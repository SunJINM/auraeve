"""Agent 工具的抽象基类。"""

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """所有 Agent 工具的抽象基类。"""

    _TYPE_MAP = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        pass

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        pass

    @property
    def metadata(self) -> dict[str, Any]:
        """Optional runtime metadata for policy/observability."""
        return {}

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        schema = self.parameters or {}
        if schema.get("type", "object") != "object":
            raise ValueError(f"Schema 必须为 object 类型，当前为 {schema.get('type')!r}")
        return self._validate(params, {**schema, "type": "object"}, "")

    def _validate(self, val: Any, schema: dict[str, Any], path: str) -> list[str]:
        t, label = schema.get("type"), path or "参数"
        if t in self._TYPE_MAP and not isinstance(val, self._TYPE_MAP[t]):
            return [f"{label} 应为 {t} 类型"]

        errors = []
        if "enum" in schema and val not in schema["enum"]:
            errors.append(f"{label} 必须为以下之一：{schema['enum']}")
        if t in ("integer", "number"):
            if "minimum" in schema and val < schema["minimum"]:
                errors.append(f"{label} 不能小于 {schema['minimum']}")
            if "maximum" in schema and val > schema["maximum"]:
                errors.append(f"{label} 不能大于 {schema['maximum']}")
        if t == "string":
            if "minLength" in schema and len(val) < schema["minLength"]:
                errors.append(f"{label} 长度不能小于 {schema['minLength']}")
            if "maxLength" in schema and len(val) > schema["maxLength"]:
                errors.append(f"{label} 长度不能大于 {schema['maxLength']}")
        if t == "object":
            props = schema.get("properties", {})
            for k in schema.get("required", []):
                if k not in val:
                    errors.append(f"缺少必填字段：{path + '.' + k if path else k}")
            for k, v in val.items():
                if k in props:
                    errors.extend(self._validate(v, props[k], path + '.' + k if path else k))
        if t == "array" and "items" in schema:
            for i, item in enumerate(val):
                errors.extend(self._validate(item, schema["items"], f"{path}[{i}]" if path else f"[{i}]"))
        return errors

    def to_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }
