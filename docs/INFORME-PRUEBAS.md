# Informe de pruebas

Fecha: 8 de octubre de 2026 · Versión 1.2.0
Equipo de pruebas: Debian 13 (trixie) x86_64 real, sesión Wayland con PipeWire, 24 hilos, 31 GB de RAM.
**No se ha dispuesto de un Windows 11 ni de un Ubuntu 24.04.** Lo que no se pudo ejecutar se indica como tal.

Cada prueba se clasifica como **superada**, **fallida** o **no ejecutable aquí**.

## 1. Pruebas automatizadas — superadas (91 de 91, ninguna omitida)

Se ejecutan con `./herramientas/probar.sh`, siempre con el Python del paquete. Usan los motores reales, no simulacros.

| Archivo | Nº | Qué comprueba |
|---|---|---|
| `test_dependencias` | 7 | El intérprete en uso es el del paquete (3.11); `sounddevice` y `soundfile` se cargan desde `runtime/`; una dependencia ausente se detecta y se nombra; con el Python del sistema el programa se niega a abrir y dice cómo arrancar; el diagnóstico no filtra rutas personales |
| `test_audio` | 14 | Señal sintética guardada idéntica muestra a muestra; pausa; cola saturada y desbordamiento notificados y toma marcada incompleta; disco lleno conserva lo grabado; WAV válido antes de cerrarse; cancelar borra; segmentos en vivo contiguos; **sesión simulada de 40 min** sin pérdidas |
| `test_partitura_flujo` | 19 | **Pentagrama:** posición de las notas en clave de Sol, Fa y Do (3.ª y 4.ª), figuras, acordes; la clave elegida y los nombres Do-Re-Mi llegan al MusicXML. Además: WAV sintético (escala de Do) → notas exactas → MIDI → MusicXML; corrección manual crea versión nueva sin tocar la anterior; nota que cruza trozos no se parte; silencio no inventa notas; archivo ilegible da error explicado; cancelación sin restos |
| `test_letras_flujo` | 8 | Audio libre en español: idioma detectado, palabras esperadas, tiempos crecientes, exportación y reimportación; idioma manual; error sin tumbar el motor; el modo «voz cantada» no da por bueno texto en música sin voz |
| `test_exportar` | 10 | SRT, VTT y LRC exactos; ida y vuelta; texto editado conserva tiempos; una línea nueva no recibe un tiempo inventado |
| `test_rutas_proyectos` | 10 | Nombres con tildes y caracteres prohibidos; nombres únicos; audio asociado a resultados; toma interrumpida marcada y conservada; solo se borran proyectos |
| `test_actualizar` | 6 | Sobre una instalación de pega: solo se ofrecen versiones más nuevas y el paquete de este sistema; descargar, aplicar y volver atrás sin tocar los datos; un paquete dañado, falso o con rutas fuera de la carpeta no cambia nada |
| `test_limpieza` | 4 | La desinstalación borra la carpeta del programa y nada más; se niega ante cualquier otra carpeta |
| `test_ui` | 13 | La ventana real sin pantalla: navegación, botones bloqueados según el estado, partitura y letra de principio a fin, **partitura en vivo** (una melodía conocida entra por el callback de audio y sus notas aparecen antes de detener; al detener se crea la definitiva), error explicado, cancelación, diagnóstico |

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

### Letra de música grabada por micrófono (caso real del usuario) — fallida por la señal, no por el programa

Una toma de 54 s de música de Spotify captada por los altavoces con un micrófono (pico del 5 %, media de −44 dB) no produjo texto. Analizada a mano: el motor responde cosas distintas en cada intento («Música», «¡Suscríbete!», versos que cambian), es decir, no hay letra recuperable y lo que sale es inventado. Cambios a raíz de esto:

- nueva entrada **«Sonido del equipo»** (Linux) que graba directamente lo que suena por una salida; verificado que el flujo queda conectado a la salida elegida. **No ejecutable aquí:** grabar con ella una canción real y medir la calidad de la letra (habría que reproducir música en tu equipo);
- aviso de **nivel muy bajo** al terminar una toma, y diálogo con pasos concretos cuando la transcripción sale vacía;
- el modo «voz cantada» ya no descarta de antemano los tramos que el modelo cree sin voz (los muestra con ⚠), pero sí el relleno inventado.

Sigue sin probarse la letra de una canción con instrumentos captada con buena señal; Whisper no está hecho para canto con música y puede fallar aunque el audio sea limpio.

### Partitura con letra (añadido después) — superada con audio de prueba

Voz real en español mezclada con una melodía sintética, en un solo archivo: salieron 82 notas, 19 de ellas con su palabra («corto», «desambiguación», «en», «wikipedia»…), visibles en el pentagrama y la tabla; una palabra corregida a mano llegó al MusicXML de la nueva versión; el texto completo se abrió en Letras. MuseScore renderizó la partitura con la letra bajo las notas.

- **Fallo encontrado y corregido:** MuseScore 4.7.5 se cerraba (violación de segmento) al abrir esa partitura, con o sin letra. Causa: los tresillos que generaba la conversión a MusicXML. Ahora se cuantiza a semicorcheas y hay una prueba de regresión.
- **No ejecutable aquí:** una canción real cantada con instrumentos. El audio de prueba es voz hablada, que al pasarla a notas da una partitura enrevesada; con canto real la colocación de las palabras depende de que Whisper las reconozca y dé bien sus tiempos.

### Interfaz de editor de partituras (1.1) — superada sin pantalla

Rediseño al estilo de un editor de notación. Probado en la ventana real sin pantalla: reparto en sistemas y compases, cambio de figura, altura por teclado, letra por nota, zoom y hoja estrecha sin perder ni repetir notas. Revisado a la vista en capturas con una melodía y con una canción con letra.

- **No ejecutable aquí:** manejo real con ratón y teclado en tu escritorio (no se abren ventanas en tu sesión).
- La versión anterior se conserva en la etiqueta `v1.0-clasica` y en la copia `PartituraLibre-v1-clasica`, que arrancó con 12 comprobaciones correctas.

### Edición y PDF sin MuseScore (añadido después) — superada sin pantalla

- Partitura escrita a mano en una hoja en blanco (introducir con clic, figura, letra), guardada como MusicXML con las notas y la letra correctas, y **reabierta** desde ese MusicXML como partitura editable idéntica.
- Deshacer y rehacer, arrastre (un arrastre = un solo paso que deshacer), desplazamiento en el tiempo.
- **PDF propio:** una melodía con letra y silencios en 1 página A4; 260 notas en 4 páginas. Revisado a la vista convirtiendo el PDF a imagen.
- **No ejecutable aquí:** el arrastre y los clics con un ratón real, y la reproducción (*▶ Oír*) por tus altavoces: no se hizo sonar nada en tu equipo.
- Fallo encontrado y corregido: al reabrir un MusicXML propio, la línea de nombres Do-Re-Mi se tomaba por letra.

### Fluidez del arrastre (añadido después) — superada con ratón simulado

Medido antes y después, por cada paso de un arrastre (incluido el repintado):

| Notas en la partitura | Antes | Después |
|---|---|---|
| 40 | 4,4 ms | 2,0 ms |
| 300 | 23,6 ms | 1,8 ms |
| 1200 | 88,1 ms | 1,9 ms |

Causa: cada paso reconstruía la tabla entera y redibujaba todos los sistemas, también los que no se veían. Ahora solo se actualiza la fila de la nota movida y se repinta su sistema; la hoja solo dibuja lo visible. Hay una prueba que arrastra con eventos de ratón sobre 1200 notas y falla si un paso supera 20 ms.

- **No ejecutable aquí:** la sensación con tu ratón y tu pantalla; las cifras son de este equipo (rápido) y sin pantalla real.

### Edición con las teclas de MuseScore (añadido después) — superada con teclado simulado

Una melodía tecleada sobre la hoja con eventos de teclado reales: N, cifras de figura, letras de nota, silencio con 0, puntillo, acorde con Mayús, letra con Ctrl+L (espacio y guion avanzan), deshacer, Esc, e inserción en medio desplazando lo que sigue sin separar cada palabra de su nota. La prueba destapó y corrigió una diferencia con MuseScore: en modo introducir, la cifra cambiaba la nota elegida en vez de fijar la figura de la siguiente.

- **No ejecutable aquí:** tu teclado físico y su distribución (el punto y las cifras del teclado numérico no se han probado).

### «Subir el volumen» de una toma floja (caso real) — no sirve

Con la última toma de letra (pico del 13 %, señal apenas 3 dB sobre el ruido de fondo) se probó amplificar, limpiar ruido y normalizar. Sin tratar no sale texto. Tratada, el motor produce texto distinto según el tratamiento («y la polsilla» ocho veces, «¡Suscríbete!», otros versos): es inventado. No se añadió un amplificador. Sí un botón *Sonido del equipo* que selecciona con un clic la captura directa de la salida; **no ejecutable aquí** comprobarlo con una canción, porque en el momento de la prueba no sonaba nada en el equipo.

### «Sonido del equipo» elegía la salida equivocada (caso real) — corregido

La lista ofrecía una entrada por cada salida de audio, y la del micrófono inalámbrico (que también tiene salida de auriculares) se confundía con el propio micrófono: al elegirla el nivel era 0 %. Ahora hay una única entrada que, al empezar, localiza la salida por la que está sonando algo (o la predeterminada si no suena nada), avisa antes de grabar si nada se está reproduciendo y da mensajes propios en vez de «acerca el micrófono». Verificado que se conecta a la salida correcta; **no ejecutable aquí** con música real, porque no sonaba nada durante la prueba.

### Actualización automática desde GitHub — superada en Linux, de punta a punta

Publicada la versión 1.2.0 en github.com/aemon1977/PartituraLibre, se montó una instalación con el número de versión rebajado a 1.1.9 y una marca propia en `app/`:

- detectó la 1.2.0 publicada, descargó el paquete de Linux (0,9 MB) y verificó el sha256 que da GitHub;
- en el arranque siguiente el lanzador la aplicó: la app pasó a 1.2.0, la anterior quedó en `app.anterior/`, y los datos y el runtime no se tocaron;
- `--deshacer-actualizacion` devolvió la instalación a la 1.1.9.

**No ejecutable aquí:** el diálogo dentro de la ventana con el botón «Reiniciar ahora» manejado a mano, y todo el proceso en Windows.

### Mejora de la voz cantada (medida con tomas reales) — superada

Dos tomas del usuario de una canción con instrumentos, capturadas por «Sonido del equipo» (pico de −7 dB), con la letra real como referencia:

| Modelo | Sin separar la voz | Con la voz separada | Tiempo (38 s de audio) |
|---|---|---|---|
| `small` | varios versos mal («con el dios», «hasta bien escribidos») | esos versos, bien | 2,5 s (+13 s de separación) |
| `medium` | mejor, con errores | casi todo bien | 8 s (+13 s) |
| `large-v3` | casi exacta | la mejor de todas | 13 s (+13 s) |

Se integró la separación de voz (modelo ONNX, sin PyTorch) como opción del modo cantado y la recomendación de `large-v3` para canciones. La prueba automatizada mezcla voz real con una melodía y exige que la separación mejore la relación voz/música en más de 6 dB y que el motor transcriba la voz separada.

- Límites observados: ningún modelo acertó un nombre propio de la letra («la cabaña del Turmo»), y a veces varias frases salen juntas en una sola línea. La letra de una canción sigue necesitando revisión.
- De paso se vio que por «Sonido del equipo» un vídeo hablado se transcribe prácticamente perfecto.

### Grabar con el micrófono lo que suena en el equipo (caso real, repetido) — la app ahora lo detecta

El usuario grabó tres veces Spotify a través de altavoces y micrófono (pico del 3–5 %), convencido de que «el sonido estaba bien» porque él lo oía bien. Ahora, si al pulsar «Grabar» hay audio sonando en el equipo y la entrada elegida es un micrófono, la app pregunta si se quiere grabar directamente el sonido del equipo y cambia la entrada sola; si durante una toma con micrófono el nivel es bajo y hay audio sonando, lo dice en directo. **No ejecutable aquí:** el resultado con música real por la vía directa (en cada intento el audio estaba en pausa).

También se corrigió que la ventana exigía 1478 px de ancho y se recortaba en una de 1418: clave, nombres y zoom pasan a la barra inferior y el mínimo queda en 1150 px.

### Micrófono con señal floja (caso real del usuario)

Todas las tomas hechas con el micrófono inalámbrico del usuario llegan con un pico del 4–5 % (−25 dB) con el volumen de entrada del sistema al 100 %. Se probó amplificar dos de ellas hasta un pico del 70 %: la de letra siguió sin dar texto y la de partitura pasó de 30 a 19 notas, sin motivo para creer que sea mejor. **Amplificar no arregla el reconocimiento**, así que no se añadió una ganancia artificial. Cambios: aviso en directo (texto y barra de nivel en ámbar) durante la prueba y la grabación, y el diálogo solo una vez por sesión.

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
- **Transcripción de una canción real con instrumentos y buena señal:** ver el caso real más arriba.

## 10. Fallidas

Ninguna en el estado entregado. Fallos encontrados por las pruebas y corregidos durante el desarrollo:

1. Tkinter del runtime portable sin fuentes suavizadas → cambio a Qt.
2. Nota «fantasma» en un armónico de la escala sintética → filtro de armónicos.
3. Nota sostenida partida al trocear audio → troceado con solape.
4. `uv` reinstalaba TensorFlow al instalar → instalación desde el bloqueo sin re-resolver.
5. MuseScore portable creaba `~/Documents/MuseScore4` y solo arranca con X11 → `HOME`/`XDG` propios y `xcb`.
6. Botones de semitono inactivos al seleccionar una nota.
8. En Linux no se podía elegir entre los micrófonos reales (solo nombres ALSA) → lista del servidor de sonido.
11. Los tresillos del MusicXML hacían que MuseScore se cerrase → cuantización a semicorcheas.
10. El pentagrama dibujaba como corchea una negra detectada algo corta → se elige la figura más cercana.
9. El borrador en vivo perdía la nota que empezaba justo en el corte entre segmentos → regla de integración corregida.
7. Lanzador de Linux: la búsqueda de Python abortaba con `set -e`.

## Qué necesito de ti

Una sola comprobación que solo puede hacerse con tu micrófono encendido:

```sh
cd PartituraLibre && ./iniciar-linux.sh
```

En **Partituras**: elige el micrófono, *Probar nivel* (la barra debe moverse al hablar) y *Grabar* 10 s tarareando: las notas deben ir apareciendo a los pocos segundos. Al *Detener* se crea sola la partitura definitiva. Si algo falla, envíame el resultado de:

```sh
./iniciar-linux.sh --diagnostico
```

y los archivos `logs/app.log` y `logs/motores.log` (no contienen audio).

En Windows 11: descomprime el ZIP, ejecuta `iniciar-windows.bat` y, si algo falla, `iniciar-windows.bat --diagnostico`.
