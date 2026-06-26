# Migraciones de base de datos

Scripts de migración SQLite one-shot aplicados durante el desarrollo incremental del proyecto.

| Script | Fase | Descripción |
|--------|------|-------------|
| `phase6_migrate.py` | 6 | Renders verticales — columnas iniciales |
| `phase7_migrate_title_text.py` | 7 | Texto de título en renders |
| `phase8_migrate_virality.py` | 8 | Puntuación de viralidad en clips |
| `add_title_position_migrate.py` | 8b | Posición del título (top/center/bottom) |
| `phase12_migrate_social.py` | 12 | Publicación en redes sociales, tokens OAuth |
| `phase13_migrate_caption_overrides.py` | 13 | Overrides de captions por clip |
| `phase14_migrate_broll_placements.py` | 14 | Posicionamiento de b-rolls en timeline |

> **Nota:** Estas migraciones ya están aplicadas a cualquier base de datos existente.
> Si comienzas desde cero, la base de datos se crea automáticamente al arrancar el backend
> (SQLAlchemy `create_all`) con el esquema completo y actual — no necesitas correr estos scripts.
> Solo son necesarios para actualizar una instalación anterior al esquema actual.
