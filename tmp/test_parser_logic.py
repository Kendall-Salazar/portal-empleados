"""Unit test for the refactored Excel importer."""
import sys, json
sys.path.insert(0, "planillas")

import horario_excel_import as hei

def test_readable_cell_to_code_manual_shift():
    """Turno excepcional debe normalizarse a MANUAL_."""
    warnings = []
    # Turno compuesto estilo "5am-11pm + 5pm + 11pm" =>  MANUAL_05-23+17-23 aprox
    code = hei.readable_cell_to_code("5am-11pm", warnings)
    assert code.startswith("MANUAL_"), f"Esperaba MANUAL_, obtuve {code}"
    print("PASS: 5am-11pm =>", code)

def test_readable_cell_to_code_off():
    warnings = []
    assert hei.readable_cell_to_code(None, warnings) == "OFF"
    assert hei.readable_cell_to_code("", warnings) == "OFF"
    assert hei.readable_cell_to_code("LIBRE", warnings) == "OFF"
    print("PASS: OFF cases")

def test_readable_cell_to_code_standard():
    """T1_05-13 and D1_05-13 share the same readable text (collision).
    The inverse map picks the first alphabetically (D1_05-13). That's correct behavior.
    Here we just verify a non-colliding standard shift resolves correctly."""
    warnings = []
    # T8_13-20 = 01:00 PM - 08:00 PM (no collision)
    code = hei.readable_cell_to_code("01:00 PM - 08:00 PM", warnings)
    assert code == "T8_13-20", f"Esperaba T8_13-20, obtuve {code}"
    print("PASS: 01:00 PM - 08:00 PM =>", code)

def test_vac_perm():
    warnings = []
    assert hei.readable_cell_to_code("VACACIONES", warnings) == "VAC"
    assert hei.readable_cell_to_code("PERMISO", warnings) == "PERM"
    print("PASS: VAC / PERM")

def test_normalize_task_label():
    assert hei._normalize_task_label("Medir tanques") == "Tanques"
    assert hei._normalize_task_label("BAÑOS") == "Baños"
    assert hei._normalize_task_label("Oficina y basureros") == "Oficina + Basureros + Baños"
    assert hei._normalize_task_label("HORARIO") is None
    print("PASS: task label normalization")

def test_build_task_label():
    assert hei._build_task_label("Baños", "↑", None) == "Baños ↑AM"
    assert hei._build_task_label("Tanques", "↓", None) == "Tanques ↓PM"
    assert hei._build_task_label("Baños", None, "T1_05-13") == "Baños ↑AM"
    assert hei._build_task_label("Baños", None, "T8_13-20") == "Baños ↓PM"
    assert hei._build_task_label("Baños", None, None) == "Baños"
    print("PASS: task label builder")

if __name__ == "__main__":
    test_readable_cell_to_code_off()
    test_readable_cell_to_code_manual_shift()
    test_readable_cell_to_code_standard()
    test_vac_perm()
    test_normalize_task_label()
    test_build_task_label()
    print("\nTodos los tests pasaron OK!")
