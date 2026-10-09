# Dependencias y licencias

El código propio de Partitura Libre es MIT (`LICENSE`). Salvo la fuente Bravura, nada de lo siguiente va dentro de los paquetes: se descarga en el primer arranque (o al pulsar un botón) desde su origen oficial, con versión y suma de verificación fijadas en `app/requisitos/*.txt`, los lanzadores y `app/partitura_libre/editor.py`.

| Componente | Para qué | Licencia | Origen |
|---|---|---|---|
| uv 0.12.23 | Obtener Python e instalar paquetes dentro de `runtime/` | MIT / Apache 2.0 | github.com/astral-sh/uv |
| CPython 3.11 (python-build-standalone) | Runtime único de la interfaz y de los motores | PSF | github.com/astral-sh/python-build-standalone |
| PySide6-Essentials 6.11 (Qt 6) | Interfaz gráfica | LGPL v3 (se usa como biblioteca dinámica sin modificar) | PyPI |
| sounddevice | Captura de audio (PortAudio) | MIT | PyPI |
| PortAudio | Biblioteca de audio: incluida en el wheel en Windows; la del sistema en Linux | MIT | — |
| PyAudioWPatch (solo Windows) | Capturar lo que suena en el equipo (WASAPI *loopback*) | MIT | PyPI |
| soundfile + libsndfile | Lectura de WAV/FLAC/OGG/MP3 | BSD 3 / LGPL 2.1 | PyPI |
| NumPy | Cálculo | BSD 3 | PyPI |
| faster-whisper, CTranslate2 | Voz a texto en CPU | MIT | PyPI |
| PyAV (FFmpeg incluido en el wheel) | Decodificar audio y vídeo importados | BSD 3 / LGPL | PyPI |
| ONNX Runtime | Ejecutar los modelos | MIT | PyPI |
| Modelos Whisper (conversión de Systran) | Voz a texto; descarga a petición | MIT | huggingface.co/Systran |
| Modelo UVR-MDX-NET-Voc_FT, de Ultimate Vocal Remover (Anjok07, aufr33 y colaboradores) | Separar la voz de los instrumentos; descarga a petición | MIT (con mención a UVR y sus autores) | github.com/TRvlvr/model_repo |
| Basic Pitch 0.4.0 (Spotify) y su modelo | Audio a notas | Apache 2.0 | PyPI |
| librosa, resampy, scipy, scikit-learn, numba | Dependencias de Basic Pitch | ISC / BSD | PyPI |
| pretty_midi, mido | Escritura de MIDI | MIT | PyPI |
| music21 | MIDI a MusicXML | BSD 3 | PyPI |
| Fuente Bravura (Steinberg) | Claves y figuras del pentagrama; **sí va incluida** en `app/partitura_libre/recursos/` | SIL Open Font License 1.1 | github.com/steinbergmedia/bravura |
| MuseScore Studio 4.7.5 (opcional) | Edición gráfica y PDF; programa aparte | GPL v3 | github.com/musescore/MuseScore |

Notas:

- **TensorFlow no se instala.** Basic Pitch 0.4.0 lo declara como dependencia, pero trae el mismo modelo en ONNX; `app/requisitos/exclusiones.txt` lo omite (≈ 1,5 GB menos) y el motor funciona con ONNX Runtime.
- **MuseScore** se ejecuta como proceso independiente (no se enlaza), por lo que su GPL no afecta al código del programa. No se redistribuye: se baja de su página oficial.
- Audios de prueba: ver `tests/datos/LICENCIAS.txt`.
