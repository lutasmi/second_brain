# second_brain / Biblioteca de Ideas

Visión

Biblioteca de Ideas es un sistema de captura, almacenamiento y consulta de conocimiento personal pensado para perdurar durante muchos años.

No pretende ser una aplicación de notas.

No pretende ser un gestor de favoritos.

Su objetivo es construir una biblioteca documental donde toda la información capturada permanezca disponible independientemente de la IA, la aplicación o la tecnología utilizada para consultarla.

Los datos son el activo.

La aplicación es reemplazable.

La IA es reemplazable.

Objetivos

* Capturar información con la mínima fricción posible.
* Conservar el contenido original siempre que sea posible.
* Almacenar la información en un formato abierto.
* Permitir la evolución tecnológica sin migraciones complejas.
* Facilitar consultas futuras mediante búsqueda clásica y búsqueda semántica.

Principios de arquitectura

Fuente de verdad

La fuente de verdad son archivos Markdown.

Nunca una base de datos.

Nunca un servicio externo.

La base de datos únicamente podrá utilizarse como índice o caché.

Debe poder reconstruirse completamente a partir de los Markdown.

Portabilidad

Toda la información debe poder abrirse con cualquier editor de texto.

No debe depender de Obsidian, Notion ni de ninguna aplicación concreta.

Obsidian podrá utilizarse como visor, nunca como dependencia tecnológica.

Simplicidad

Siempre debe preferirse la solución más sencilla que cumpla el objetivo.

Evitar sobreingeniería.

Evitar dependencias innecesarias.

Evitar frameworks complejos cuando una solución simple sea suficiente.

MVP

La primera versión únicamente necesita soportar:

* Texto
* URLs

Flujo esperado:

Telegram

↓

Procesamiento

↓

Markdown

Todavía no son prioritarios:

* OCR
* Audio
* Vídeo
* Embeddings
* RAG
* Agentes IA

Arquitectura objetivo

Captura

↓

Procesamiento

↓

Markdown (fuente maestra)

↓

Índice

↓

Búsqueda

↓

IA

Evolución prevista

Fase 1

* Telegram
* Texto
* URLs
* Markdown

Fase 2

* Extracción de contenido de páginas web
* Twitter/X
* YouTube
* LinkedIn

Fase 3

* PDFs
* Imágenes
* OCR
* Audio
* Transcripción

Fase 4

* Índice
* Embeddings
* Búsqueda semántica
* Chat sobre la biblioteca

Filosofía de desarrollo

Antes de añadir nuevas funcionalidades, debe garantizarse que:

* La captura funciona.
* Los Markdown son correctos.
* La información nunca se pierde.
* El sistema puede ejecutarse de extremo a extremo.

La prioridad siempre será disponer de un producto funcional antes que de una arquitectura perfecta.
