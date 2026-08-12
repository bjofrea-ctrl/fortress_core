"""HardinessChecker — validación de respuestas LLM.

Extraído intacto de prompt_engine.py (659 líneas muertas, eliminado): era lo
único en uso de ese módulo, importado por triad_agents.py. Comportamiento
inalterado.
"""
import json
import re
from typing import Dict, List, Optional, Tuple


class HardinessChecker:
    """
    Sistema de validación de respuestas LLM:
    1. Schema validation — JSON válido con campos requeridos
    2. Range validation — scores dentro de rangos esperados
    3. Consistency validation — no contradice datos deterministas
    4. Hallucination detection — detecta números inventados
    5. Confidence calibration — confianza coherente con score
    """

    REQUIRED_FIELDS = {
        "score": (float, lambda x: -1.0 <= x <= 1.0),
        "confidence": (float, lambda x: 0.0 <= x <= 1.0),
        "reasoning": (str, lambda x: len(x) > 10),
    }

    @staticmethod
    def validate_fields(data: Dict) -> List[str]:
        """Valida un dict ya parseado contra REQUIRED_FIELDS (tipo + rango)."""
        errors = []
        for field_name, (field_type, validator) in HardinessChecker.REQUIRED_FIELDS.items():
            if field_name not in data:
                errors.append(f"Campo requerido faltante: {field_name}")
                continue
            value = data[field_name]
            if not isinstance(value, field_type):
                errors.append(f"Campo {field_name} tiene tipo incorrecto: {type(value).__name__}")
                continue
            if not validator(value):
                errors.append(f"Campo {field_name} fuera de rango: {value}")
        return errors

    @staticmethod
    def validate_json_response(response: str) -> Tuple[Optional[Dict], List[str]]:
        """Valida que la respuesta sea JSON válido con campos requeridos."""
        try:
            # Extraer JSON del texto
            start = response.find("{")
            end = response.rfind("}") + 1
            if start < 0 or end <= start:
                return None, ["No se encontró JSON en la respuesta"]

            data = json.loads(response[start:end])
        except json.JSONDecodeError as e:
            return None, [f"JSON inválido: {str(e)}"]

        errors = HardinessChecker.validate_fields(data)
        return data if not errors else None, errors

    @staticmethod
    def validate_against_deterministic(llm_score: float, deterministic_score: float,
                                       max_deviation: float = 0.5) -> Tuple[bool, str]:
        """
        Valida que el score LLM no se desvíe demasiado del determinista.
        Si el LLM se desvía mucho, probablemente está alucinando.
        """
        deviation = abs(llm_score - deterministic_score)
        if deviation > max_deviation:
            return False, f"Desviación excesiva: LLM={llm_score:+.3f} vs determinista={deterministic_score:+.3f}"
        return True, f"Desviación aceptable: {deviation:.3f}"

    @staticmethod
    def validate_confidence_consistency(score: float, confidence: float) -> Tuple[bool, str]:
        """
        Valida que la confianza sea coherente con la magnitud del score.
        Un score cercano a 0 con confianza alta es sospechoso.
        """
        if abs(score) < 0.1 and confidence > 0.8:
            return False, f"Confianza alta ({confidence:.2f}) con score neutral ({score:+.3f})"
        if abs(score) > 0.7 and confidence < 0.3:
            return False, f"Confianza baja ({confidence:.2f}) con score extremo ({score:+.3f})"
        return True, ""

    @staticmethod
    def detect_hallucination(text: str, known_values: Dict[str, float]) -> List[str]:
        """Detecta números en el texto que no coinciden con datos conocidos."""
        hallucinations = []
        for key, known_value in known_values.items():
            # Buscar el número cerca de la clave
            pattern = rf"{key}[\s:=]+([-+]?\d+\.?\d*)"
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                try:
                    val = float(m)
                    if known_value and abs(val - known_value) / max(abs(known_value), 1) > 0.2:
                        hallucinations.append(
                            f"Posible alucinación: {key}={val} vs real={known_value:.2f}"
                        )
                except ValueError:
                    pass
        return hallucinations