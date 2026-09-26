"""C3: RAGMemorySystem as_of (TradingAgents decision_log.py #1251)."""
from app.core.knowledge_repo import RAGMemorySystem


def test_record_lesson_stores_resolution_date(tmp_path):
    mem = RAGMemorySystem(str(tmp_path / "rag.json"))
    mem.record_lesson(
        agent="BULL", lesson="lesson A", context="ctx", outcome="ok", resolution_date="2030-01-01"
    )
    assert mem.lesson_history[-1]["resolution_date"] == "2030-01-01"
    # agent_knowledge guarda dict con resolution_date
    assert mem.agent_knowledge["BULL"][-1]["resolution_date"] == "2030-01-01"
    assert mem.agent_knowledge["BULL"][-1]["text"] == "lesson A"


def test_record_lesson_defaults_to_today(tmp_path):
    from datetime import date

    mem = RAGMemorySystem(str(tmp_path / "rag2.json"))
    mem.record_lesson(agent="BEAR", lesson="lesson default", context="ctx", outcome="ok")
    assert mem.lesson_history[-1]["resolution_date"] == date.today().isoformat()


def test_retrieve_filters_future_lesson_as_of(tmp_path):
    """Lección 2030 no aparece en as_of 2026-01-01 (C3)."""
    mem = RAGMemorySystem(str(tmp_path / "rag3.json"))
    mem.record_lesson(
        agent="BULL",
        lesson="lección futura 2030 sobre momentum extremo",
        context="ctx",
        outcome="ok",
        resolution_date="2030-01-01",
    )
    mem.record_lesson(
        agent="BULL",
        lesson="lección pasada 2025 sobre momentum extremo",
        context="ctx",
        outcome="ok",
        resolution_date="2025-06-01",
    )
    result = mem.retrieve_agent_memory(agent="BULL", query="momentum", as_of="2026-01-01")
    assert "futura" not in result
    assert "pasada" in result


def test_retrieve_without_as_of_shows_all(tmp_path):
    mem = RAGMemorySystem(str(tmp_path / "rag4.json"))
    mem.record_lesson(agent="BEAR", lesson="bear lesson futura", context="ctx", outcome="ok", resolution_date="2030-01-01")
    mem.record_lesson(agent="BEAR", lesson="bear lesson pasada", context="ctx", outcome="ok", resolution_date="2025-01-01")
    result = mem.retrieve_agent_memory(agent="BEAR", query="bear lesson", as_of=None)
    assert "futura" in result
    assert "pasada" in result


def test_get_memory_context_respects_as_of(tmp_path):
    mem = RAGMemorySystem(str(tmp_path / "rag5.json"))
    mem.record_lesson(agent="CONTRARIAN", lesson="contrarian futura", context="ctx", outcome="ok", resolution_date="2030-12-31")
    mem.record_lesson(agent="CONTRARIAN", lesson="contrarian pasada", context="ctx", outcome="ok", resolution_date="2024-01-01")
    ctx = mem.get_memory_context(agent="CONTRARIAN", query="contrarian", as_of="2026-01-01")
    assert "futura" not in ctx
    assert "pasada" in ctx
    ctx_all = mem.get_memory_context(agent="CONTRARIAN", query="contrarian", as_of=None)
    assert "futura" in ctx_all


def test_persistence_roundtrip_keeps_resolution_date(tmp_path):
    p = str(tmp_path / "rag6.json")
    mem = RAGMemorySystem(p)
    mem.record_lesson(agent="BULL", lesson="persist futura", context="ctx", outcome="ok", resolution_date="2030-01-01")
    mem.record_lesson(agent="BULL", lesson="persist pasada", context="ctx", outcome="ok", resolution_date="2025-01-01")
    # recargar desde disco
    mem2 = RAGMemorySystem(p)
    result = mem2.retrieve_agent_memory(agent="BULL", query="persist", as_of="2026-01-01")
    assert "futura" not in result
    assert "pasada" in result


def test_legacy_str_entry_excluded_under_as_of(tmp_path):
    """Entradas legacy sin fecha se excluyen cuando hay filtro as_of."""
    mem = RAGMemorySystem(str(tmp_path / "rag7.json"))
    # simular legacy: inyectar str directamente
    mem.agent_knowledge["BULL"] = ["legacy lesson momentum"]
    result = mem.retrieve_agent_memory(agent="BULL", query="momentum", as_of="2026-01-01")
    # sin fecha conocida no puede garantizar look-ahead safety -> excluida
    assert result == ""
    # sin filtro debe aparecer
    result2 = mem.retrieve_agent_memory(agent="BULL", query="momentum", as_of=None)
    assert "legacy" in result2
