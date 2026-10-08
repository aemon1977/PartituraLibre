# Informe de pruebas

Fecha: 8 de octubre de 2026 · Versión 1.0.0
Equipo de pruebas: Debian 13 (trixie) x86_64 real, sesión Wayland con PipeWire, 24 hilos, 31 GB de RAM.
**No se ha dispuesto de un Windows 11 ni de un Ubuntu 24.04.** Lo que no se pudo ejecutar se indica como tal.

Cada prueba se clasifica como **superada**, **fallida** o **no ejecutable aquí**.

## 1. Pruebas automatizadas — superadas (66 de 66, ninguna omitida)

Se ejecutan con `./herramientas/probar.sh`, siempre con el Python del paquete. Usan los motores reales, no simulacros.

| Archivo | Nº | Qué comprueba |
|---|---|---|
| `test_dependencias` | 7 | El intérprete en uso es el del paquete (3.11); `sounddevice` y `soundfile` se cargan desde `runtime/`; una dependencia ausente se detecta y se nombra; con el Python del sistema el programa se niega a abrir y dice cómo arrancar; el diagnóstico no filtra rutas personales |
| `test_audio` | 11 | Señal sintética guardada idéntica muestra a muestra; pausa; cola saturada y desbordamiento notificados y toma marcada incompleta; disco lleno conserva lo grabado; WAV válido antes de cerrarse; cancelar borra; segmentos en vivo contiguos; **sesión simulada de 40 min** sin pérdidas |
| `test_partitura_flujo` | 12 | **Pentagrama:** posición de las notas en clave de Sol, Fa y Do (3.ª y 4.ª), figuras, acordes; la clave elegida y los nombres Do-Re-Mi llegan al MusicXML. Además: | WAV sintético (escala de Do) → notas exactas → MIDI → MusicXML; corrección manual crea versión nueva sin tocar la anterior; nota que cruza trozos no se parte; silencio no inventa notas; archivo ilegible da error explicado; cancelación sin restos |
| `test_letras_flujo` | 6 | Audio libre en español: idioma detectado, palabras esperadas, tiempos crecientes, exportación y reimportación; idioma manual; error sin tumbar el motor; el modo «voz cantada» no da por bueno texto en música sin voz |
| `test_exportar` | 9 | SRT, VTT y LRC exactos; ida y vuelta; texto editado conserva tiempos; una línea nueva no recibe un tiempo inventado |
| `test_rutas_proyectos` | 10 | Nombres con tildes y caracteres prohibidos; nombres únicos; audio asociado a resultados; toma interrumpida marcada y conservada; solo se borran proyectos |
| `test_limpieza` | 4 | La desinstalación borra la carpeta del programa y nada más; se niega ante cualquier otra carpeta |
| `test_ui` | 7 | La ventana real sin pantalla: navegación, botones bloqueados según el estado, partitura y letra de principio a fin, **partitura en vivo** (una melodía conocida entra por el callback de audio y sus notas aparecen antes de detener; al detener se crea la definitiva), error explicado, cancelación, diagnóstico |

## 2. Instalación desde cero en Debian 13 — superada

Paquete del proyecto descomprimido en `Prueba limpia áé ñ/PartituraLibre`, lanzado con `HOME` vacío y `PATH=/usr/bin:/bin` (sin `uv` ni nada del usuario al alcance):

- `./iniciar-linux.sh --si --diagnostico` descargó uv, Python 3.11 y los dos conjuntos en 17 s y dio 10 comprobaciones OK y 2 avisos esperados (sin modelo de voz ni MuseScore aún).
- La ventana se abrió mediante el lanzador (modo sin pantalla) y seguía viva al cortarla a los 8 s.
- Las pruebas automatizadas pasaron dentro de esa instalación.
- **Escrituras fuera de la carpeta: ninguna.** El `HOME` de prueba quedó vacío y no apareció nada nuevo en `/tmp`.
  (En la primera pasada la biblioteca PulseAudio del sistema creó `~/.config/pulse/cookie`; se corrigió y se repitió la prueba con `HOME` vacío.)

## 3. Mover la carpeta y uso sin Internet — superada

La carpeta se renombró a `Movida a otra ruta (ó)` y se ejecutó dentro de un espacio de red aislado (`unshare -rn`, comprobado que no había conexión): diagnóstico correcto y todas las pruebas superadas, incluidas partitura y voz.

## 4. Borrado — superada

Tras borrar la carpeta de prueba (1,6 GB): 0 archivos en el `HOME` de prueba, 0 en `/tmp`, 0 procesos vivos. No se tocó nada del sistema.

## 5. Grabación real con micrófono — superada en parte

Con los dispositivos `default` y `pulse` del equipo se grabaron 4 s con 1 s de pausa: archivos de 2,95 s y 3,00 s a 44,1 kHz, 0 desbordes, 0 muestras perdidas. El dispositivo `hw:` directo estaba ocupado por PipeWire y la app dio el mensaje previsto.

**Elección de micrófono (añadida después):** la app lista los dos micrófonos reales del equipo por su nombre («G435 Wireless Gaming Headset Mono» y «Starship/Matisse HD Audio Controller Estéreo analógico»). Grabando con cada uno, el servidor de sonido confirmó que el flujo estaba conectado al micrófono pedido.

**Límite de esta prueba:** la señal recibida fue silencio absoluto (el micrófono del equipo estaba apagado o silenciado), así que queda verificada la captura en tiempo real pero no el contenido sonoro. A raíz de esto la app avisa ahora cuando una toma queda muda. Ver «Qué necesito de ti».

## 6. MuseScore portable y PDF — superada (Linux)

Descarga de 195 MB con sha256, extracción en `runtime/musescore` y exportación a PDF de un MusicXML y de un MIDI generados por la app (PDF válidos; la partitura de la escala se revisó a la vista: ocho negras de Do4 a Do5 en 4/4). Con `HOME` vacío no escribió nada fuera de la carpeta.

- **No ejecutable aquí:** la edición interactiva en la ventana de MuseScore (no se abrieron ventanas en tu escritorio).

### Pentagrama (añadido después)

Revisado a la vista en las cuatro claves con una escala, figuras de redonda a semicorchea, un sostenido y un acorde; y dentro de la app con una melodía conocida (Mi Mi Fa Sol Sol Fa Mi Re Do…). Un MusicXML generado en clave de Do en 3.ª con nombres se renderizó en MuseScore con la clave y los nombres correctos.

## 7. Comparación de modelos de voz — superada

Mismo audio (25 s en español + 11 s en inglés), CPU, incluida la carga del modelo:

| Modelo | Tiempo | Resultado en español |
|---|---|---|
| `tiny` (75 MB) | 1,6 s | «…en Wikipedia, la incyclope de al libre» (con errores) |
| `small` (485 MB) | 6,1 s | «…en wikipedia la enciclopedia libre» (correcto) |

Ambos detectaron bien el idioma. Por eso `small` es el predeterminado.

## 8. Windows 11 — no ejecutable aquí

No hay Windows en este entorno. **No se declara validado.** Como aproximación se usó Wine 10 con un prefijo temporal:

| Paso | Resultado bajo Wine |
|---|---|
| `iniciar-windows.bat` en una ruta con «ñ» | superada (tras corregir dos fallos que la prueba destapó: detección de 64 bits y búsqueda del intérprete) |
| `uv` instala Python 3.11 de Windows en `runtime\python` | superada |
| Instalación con hashes de los dos conjuntos de paquetes de Windows | superada |
| Importación del conjunto «partituras» (Basic Pitch, ONNX Runtime, music21) | superada |
| Comprobación previa de dependencias | superada: detectó y explicó el fallo siguiente |
| Carga de Qt y NumPy 2 | **no ejecutable aquí**: a Wine le faltan `icuuc.dll` y `ucrtbase.crealf`, que Windows 10/11 sí incluyen |
| Descarga de uv con `curl`/`tar`/`certutil` del lanzador | **no ejecutable aquí** (Wine no los trae; se precargó `uv.exe`) |
| Ventana, micrófono (WASAPI), MuseScore `.paf.exe`, desinstalación | **no ejecutable aquí** |

## 9. Otras no ejecutables aquí

- **Ubuntu 24.04:** sin probar. Usa los mismos binarios (glibc compatible).
- **Debian sin `libportaudio2` o sin `libxcb-cursor0`:** este equipo los tiene; el mensaje de PortAudio ausente no se ha visto en un sistema real.
- **Sesión larga en tiempo real** (horas con un micrófono): solo la simulada de 40 min.
- **Dictado y partitura en vivo con un micrófono con señal:** el camino completo está probado con una melodía sintética que entra por el mismo callback, no con sonido real.
- **Transcripción de una canción real con instrumentos:** sin audio libre adecuado; el modo cantado se probó con voz hablada y con música sin voz.

## 10. Fallidas

Ninguna en el estado entregado. Fallos encontrados por las pruebas y corregidos durante el desarrollo:

1. Tkinter del runtime portable sin fuentes suavizadas → cambio a Qt.
2. Nota «fantasma» en un armónico de la escala sintética → filtro de armónicos.
3. Nota sostenida partida al trocear audio → troceado con solape.
4. `uv` reinstalaba TensorFlow al instalar → instalación desde el bloqueo sin re-resolver.
5. MuseScore portable creaba `~/Documents/MuseScore4` y solo arranca con X11 → `HOME`/`XDG` propios y `xcb`.
6. Botones de semitono inactivos al seleccionar una nota.
8. En Linux no se podía elegir entre los micrófonos reales (solo nombres ALSA) → lista del servidor de sonido.
10. El pentagrama dibujaba como corchea una negra detectada algo corta → se elige la figura más cercana.
9. El borrador en vivo perdía la nota que empezaba justo en el corte entre segmentos → regla de integración corregida.
7. Lanzador de Linux: la búsqueda de Python abortaba con `set -e`.

## Qué necesito de ti

Una sola comprobación que solo puede hacerse con tu micrófono encendido:

```sh
cd /media/aemon77/dockerjuegos/Partituras/PartituraLibre && ./iniciar-linux.sh
```

En **Partituras**: elige el micrófono, *Probar nivel* (la barra debe moverse al hablar) y *Grabar* 10 s tarareando: las notas deben ir apareciendo a los pocos segundos. Al *Detener* se crea sola la partitura definitiva. Si algo falla, envíame el resultado de:

```sh
./iniciar-linux.sh --diagnostico
```

y los archivos `logs/app.log` y `logs/motores.log` (no contienen audio).

En Windows 11: descomprime el ZIP, ejecuta `iniciar-windows.bat` y, si algo falla, `iniciar-windows.bat --diagnostico`.
