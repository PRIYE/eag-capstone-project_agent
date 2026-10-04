"""
AI Model integrations for the AgentSwitch agent
Supports OpenAI, Anthropic, and Google models

All three model classes accept/return OpenAI-style chat messages:
  - input:  [{"role": "system"|"user"|"assistant"|"tool", "content": ..., "tool_calls": [...]}]
  - output: {"choices": [{"message": {"role": "assistant", "content": ..., "tool_calls": [...]}}]}

This lets agent/loop.py stay provider-agnostic. Anthropic and Google have
their own wire formats internally, so each class translates in both
directions (request AND response) rather than only handling one side -
without that, tool calls silently stop working after the first turn.
"""
import json
import os
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod


class AIModel(ABC):
    """Abstract base class for AI models"""

    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], tools: Optional[List[Dict]] = None,
              force_tool: Optional[str] = None) -> Dict:
        """
        Send chat completion request.

        `force_tool`, when set, forces the model to call exactly that
        tool this turn (used by agent/loop.py near the step/deadline
        budget to force `record_finding` - contracts/agent-tools.md
        "Loop-level contract": forced tool_choice in the last 2 turns
        or last 20s).
        """
        pass


class OpenAIModel(AIModel):
    """OpenAI API client"""
    
    def __init__(self, api_key: str, model: str = "gpt-4"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.openai.com/v1"
    
    def chat(self, messages: List[Dict[str, str]], tools: Optional[List[Dict]] = None,
             force_tool: Optional[str] = None) -> Dict:
        payload = {
            "model": self.model,
            "messages": self._sanitize_messages(messages),
            "temperature": 0.1
        }
        
        if tools:
            payload["tools"] = tools
            if force_tool:
                payload["tool_choice"] = {"type": "function", "function": {"name": force_tool}}
            else:
                payload["tool_choice"] = "auto"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        return self._make_request("/chat/completions", payload, headers)
    
    def _sanitize_messages(self, messages: List[Dict]) -> List[Dict]:
        """
        Strip internal-only keys (e.g. "_tool_name", used by GoogleModel's
        message translation) before sending to OpenAI. OpenAI's API
        validates the message schema strictly - an unrecognized field on a
        message object causes a 400, so we can't just forward loop.py's
        internal conversation_history dicts as-is.
        """
        allowed = {"role", "content", "tool_calls", "tool_call_id", "name"}
        sanitized = []
        for msg in messages:
            clean_msg = {k: v for k, v in msg.items() if k in allowed}
            if "tool_calls" in clean_msg and clean_msg["tool_calls"]:
                clean_msg["tool_calls"] = [
                    {k: v for k, v in tc.items() if not k.startswith("_")}
                    for tc in clean_msg["tool_calls"]
                ]
            sanitized.append(clean_msg)
        return sanitized
    
    def _make_request(self, endpoint: str, data: Dict, headers: Dict) -> Dict:
        url = f"{self.base_url}{endpoint}"
        req = urllib.request.Request(
            url, 
            data=json.dumps(data).encode(),
            headers=headers,
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            raise Exception(f"OpenAI API error {e.code}: {error_body}")


class AnthropicModel(AIModel):
    """Anthropic Claude API client"""
    
    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.anthropic.com/v1"
    
    def chat(self, messages: List[Dict[str, str]], tools: Optional[List[Dict]] = None,
             force_tool: Optional[str] = None) -> Dict:
        system_message, converted_messages = self._convert_messages_from_openai(messages)
        
        payload = {
            "model": self.model,
            "messages": converted_messages,
            "max_tokens": 4000,
            "temperature": 0.1
        }
        
        if system_message:
            payload["system"] = system_message.strip()
        
        if tools:
            payload["tools"] = self._convert_tools(tools)
            if force_tool:
                payload["tool_choice"] = {"type": "tool", "name": force_tool}
            else:
                payload["tool_choice"] = {"type": "auto"}
        
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        
        raw = self._make_request("/messages", payload, headers)
        return self._normalize_to_openai_shape(raw)
    
    def _convert_messages_from_openai(self, messages: List[Dict]) -> (str, List[Dict]):
        """
        Translate agent/loop.py's OpenAI-shaped conversation history into
        Anthropic's format:
          - system messages -> collected into a top-level `system` string
          - assistant messages with tool_calls -> content blocks of
            {"type": "text"} + {"type": "tool_use", id, name, input}
          - role "tool" messages -> a "user" message with a
            {"type": "tool_result", tool_use_id, content} block
            (Anthropic has no "tool" role; results come back as user turns)
        """
        system_message = ""
        converted: List[Dict] = []
        
        for msg in messages:
            role = msg.get("role")
            
            if role == "system":
                system_message += (msg.get("content") or "") + "\n"
            
            elif role == "assistant" and msg.get("tool_calls"):
                blocks = []
                if msg.get("content"):
                    blocks.append({"type": "text", "text": msg["content"]})
                for tc in msg["tool_calls"]:
                    func = tc.get("function", {})
                    try:
                        tool_input = json.loads(func.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        tool_input = {}
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id"),
                        "name": func.get("name"),
                        "input": tool_input
                    })
                converted.append({"role": "assistant", "content": blocks})
            
            elif role == "tool":
                converted.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id"),
                        "content": msg.get("content", "")
                    }]
                })
            
            else:
                # plain user/assistant text message
                converted.append({"role": role, "content": msg.get("content") or ""})
        
        return system_message, converted
    
    def _convert_tools(self, openai_tools: List[Dict]) -> List[Dict]:
        """Convert OpenAI tool format to Anthropic format"""
        anthropic_tools = []
        for tool in openai_tools:
            if tool.get("type") == "function":
                func = tool["function"]
                anthropic_tools.append({
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {})
                })
        return anthropic_tools
    
    def _normalize_to_openai_shape(self, raw: Dict) -> Dict:
        """Convert Anthropic's response (content blocks) into the OpenAI
        choices[0].message shape that agent/loop.py understands."""
        content_blocks = raw.get("content", [])
        text_parts = []
        tool_calls = []
        
        for block in content_blocks:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append({
                    "id": block.get("id"),
                    "type": "function",
                    "function": {
                        "name": block.get("name"),
                        "arguments": json.dumps(block.get("input", {}))
                    }
                })
        
        message = {"role": "assistant", "content": "\n".join(text_parts) or None}
        if tool_calls:
            message["tool_calls"] = tool_calls
        
        return {"choices": [{"message": message}], "_raw_provider_response": raw}
    
    def _make_request(self, endpoint: str, data: Dict, headers: Dict) -> Dict:
        url = f"{self.base_url}{endpoint}"
        req = urllib.request.Request(
            url, 
            data=json.dumps(data).encode(),
            headers=headers,
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            raise Exception(f"Anthropic API error {e.code}: {error_body}")


class GoogleModel(AIModel):
    """Google Gemini API client"""
    
    def __init__(self, api_key: str, model: str = "gemini-2.5-pro"):
        self.api_key = api_key
        self.model = model
        self.base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
    
    def chat(self, messages: List[Dict[str, str]], tools: Optional[List[Dict]] = None,
             force_tool: Optional[str] = None) -> Dict:
        system_instruction, contents = self._convert_messages_from_openai(messages)
        
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 4000
            }
        }
        
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        
        if tools:
            payload["tools"] = [{"functionDeclarations": self._convert_tools(tools)}]
            if force_tool:
                payload["toolConfig"] = {"functionCallingConfig": {
                    "mode": "ANY", "allowedFunctionNames": [force_tool]}}
        
        raw = self._make_request(f":generateContent?key={self.api_key}", payload)
        return self._normalize_to_openai_shape(raw)
    
    def _convert_messages_from_openai(self, messages: List[Dict]) -> (str, List[Dict]):
        """
        Translate OpenAI-shaped history into Gemini's `contents` list:
          - system -> systemInstruction (returned separately)
          - assistant with tool_calls -> a "model" turn with functionCall parts
          - role "tool" -> a "user" turn with a functionResponse part
        """
        system_instruction = ""
        contents: List[Dict] = []
        
        for msg in messages:
            role = msg.get("role")
            
            if role == "system":
                system_instruction += (msg.get("content") or "") + "\n"
            
            elif role == "assistant" and msg.get("tool_calls"):
                parts = []
                if msg.get("content"):
                    parts.append({"text": msg["content"]})
                for tc in msg["tool_calls"]:
                    func = tc.get("function", {})
                    try:
                        args = json.loads(func.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        args = {}
                    
                    if "_raw_part" in tc:
                        # Just send back the exact part we received!
                        parts.append(tc["_raw_part"])
                    else:
                        fc = {"name": func.get("name"), "args": args}
                        parts.append({"functionCall": fc})
                contents.append({"role": "model", "parts": parts})
            
            elif role == "tool":
                # Gemini associates function responses by name, not call id
                name = msg.get("_tool_name", "unknown_tool")
                try:
                    response_payload = json.loads(msg.get("content", "{}"))
                except json.JSONDecodeError:
                    response_payload = {"result": msg.get("content", "")}
                
                # We also need to send back the thought_signature in the functionResponse if it exists?
                # Actually, Gemini 2.5 expects the thought_signature in the functionResponse? No, the error says "in functionCall parts"
                # Wait, the error is: "Function call is missing a thought_signature in functionCall parts... function call `default_api:company_context` , position 2"
                # Position 2 means the second part of the contents array.
                contents.append({
                    "role": "user",
                    "parts": [{"functionResponse": {"name": name, "response": response_payload}}]
                })
            
            else:
                gem_role = "model" if role == "assistant" else "user"
                contents.append({"role": gem_role, "parts": [{"text": msg.get("content") or ""}]})
        
        return system_instruction.strip(), contents
    
    def _convert_tools(self, openai_tools: List[Dict]) -> List[Dict]:
        """Convert OpenAI tool format to Gemini functionDeclarations format"""
        declarations = []
        for tool in openai_tools:
            if tool.get("type") == "function":
                func = tool["function"]
                declarations.append({
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters", {})
                })
        return declarations
    
    def _normalize_to_openai_shape(self, raw: Dict) -> Dict:
        """Convert Gemini's candidates[0].content.parts into the OpenAI
        choices[0].message shape that agent/loop.py understands."""
        candidates = raw.get("candidates", [])
        if not candidates:
            return {"choices": [{"message": {"role": "assistant", "content": None}}], "_raw_provider_response": raw}
        
        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = []
        tool_calls = []
        
        for i, part in enumerate(parts):
            if "text" in part:
                text_parts.append(part["text"])
            elif "functionCall" in part:
                fc = part["functionCall"]
                # Print the raw functionCall from Gemini to see what it contains
                # print(f"DEBUG raw functionCall: {fc}")
                tc = {
                    "id": f"gemini_call_{i}",
                    "type": "function",
                    "function": {
                        "name": fc.get("name"),
                        "arguments": json.dumps(fc.get("args", {}))
                    }
                }
                # Grab the thought_signature if it's there
                # It might be at the part level or inside functionCall
                # Wait! Gemini 2.5 returns thought in a separate part before the functionCall?
                # Or maybe it's inside the functionCall? Let's just grab everything that looks like a thought signature.
                # Actually, the error says: "missing a thought_signature in functionCall parts"
                # So we need to put it IN the functionCall part when sending it back.
                # Let's save the whole raw part.
                tc["_raw_part"] = part
                tool_calls.append(tc)
        
        message = {"role": "assistant", "content": "\n".join(text_parts) or None}
        if tool_calls:
            message["tool_calls"] = tool_calls
        
        return {"choices": [{"message": message}], "_raw_provider_response": raw}
    
    def _make_request(self, endpoint: str, data: Dict) -> Dict:
        # Gemini 1.5 Pro requires v1beta, but the model name should just be gemini-1.5-pro
        # We need to ensure we're using the correct format for the URL
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}{endpoint}"
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            raise Exception(f"Google API error {e.code}: {error_body}")


def create_model() -> AIModel:
    """Create AI model from environment variables"""
    from .mcp_client import load_env
    
    env = load_env()
    provider = env.get('MODEL_PROVIDER', 'openai').lower()
    
    if provider == 'openai':
        api_key = env.get('OPENAI_API_KEY')
        if not api_key:
            raise Exception("OPENAI_API_KEY not found in .env")
        model_name = env.get('MODEL_NAME', 'gpt-4')
        return OpenAIModel(api_key, model_name)
    
    elif provider == 'anthropic':
        api_key = env.get('ANTHROPIC_API_KEY')
        if not api_key:
            raise Exception("ANTHROPIC_API_KEY not found in .env")
        model_name = env.get('MODEL_NAME', 'claude-3-5-sonnet-20241022')
        return AnthropicModel(api_key, model_name)
    
    elif provider == 'google':
        api_key = env.get('GOOGLE_API_KEY')
        if not api_key:
            raise Exception("GOOGLE_API_KEY not found in .env")
        model_name = env.get('MODEL_NAME', 'gemini-2.5-pro')
        return GoogleModel(api_key, model_name)
    
    else:
        raise Exception(f"Unknown model provider: {provider}")


def openai_tool_from_mcp(mcp_tool: Dict) -> Dict:
    """Convert MCP tool schema to OpenAI function calling format"""
    return {
        "type": "function",
        "function": {
            "name": mcp_tool["name"],
            "description": mcp_tool.get("description", ""),
            "parameters": mcp_tool.get("inputSchema", {})
        }
    }


if __name__ == "__main__":
    # Test model creation
    try:
        model = create_model()
        
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is the capital of France?"}
        ]
        
        response = model.chat(messages)
        print("Model test response:")
        print(json.dumps(response, indent=2))
        
    except Exception as e:
        print(f"Model test error: {e}")
        print("\nMake sure you have added your API key to the .env file")