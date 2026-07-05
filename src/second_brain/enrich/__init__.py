"""Enriquecimiento transversal de notas (etiquetado, relaciones...).

A diferencia de los procesadores (uno por tipo de contenido), estos módulos
se aplican a cualquier nota ya procesada. El fallo de un enriquecimiento
nunca bloquea la captura: deja la nota `pending` para reintentos.
"""
