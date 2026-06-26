# Tests

El backend tiene 61 tests que corren en cualquier plataforma sin hardware especial.

## Ejecutar tests

```bash
cd backend
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

# Tests de detección de hardware
python tests/test_cross_platform.py

# Tests unitarios
pytest tests/unit/

# Tests de integración
pytest tests/integration/

# Tests end-to-end
pytest tests/e2e/

# Todos los tests
pytest
```

## Cobertura

El proyecto requiere mínimo **79% de cobertura** (configurado en `pyproject.toml`). Los módulos GPU-dependentes están excluidos del mínimo.

## Estructura

| Carpeta | Cantidad | Qué prueba |
|---------|----------|------------|
| `tests/unit/` | 10 archivos | Servicios, validadores |
| `tests/integration/` | 9 archivos | Endpoints API |
| `tests/e2e/` | 7 archivos | Pipeline completo |

### E2E por fase

```bash
# Fase 6: presets + watermark
python tests/e2e/test_phase6_presets_watermark.py

# Fase 8: AI virality score
python tests/e2e/test_phase8_virality.py

# Fase 9: estilos de subtítulos OpusClips
python tests/e2e/test_phase9_substyles.py
```

## Migraciones de BD

Los scripts `phase*_migrate.py` agregan columnas a la base de datos SQLite. Son idempotentes (se pueden ejecutar múltiples veces).
