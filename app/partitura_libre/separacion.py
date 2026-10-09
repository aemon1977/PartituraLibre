"""Separación de la voz y los instrumentos de una canción, para que el motor de voz entienda
mejor la letra. Usa un modelo MDX-Net en ONNX (UVR-MDX-NET-Voc_FT, del proyecto Ultimate Vocal
Remover, licencia MIT) con numpy y ONNX Runtime, que ya forman parte del conjunto «app»."""
import shutil

from . import descargas, rutas

CARPETA = rutas.MODELOS / "separacion"
ARCHIVO = CARPETA / "UVR-MDX-NET-Voc_FT.onnx"
URL = "https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/UVR-MDX-NET-Voc_FT.onnx"
SHA256 = "534b2070fcc7df514b13ef660dc8cbb328679c2374d04354a5c42bb14ecce111"
MB = 64
CREDITO = "Modelo UVR-MDX-NET-Voc_FT de Ultimate Vocal Remover (Anjok07, aufr33 y colaboradores), licencia MIT."
SR = 44100


def instalado():
    return ARCHIVO.is_file()


def descargar(progreso=None, cancelar=None):
    descargas.descargar(URL, ARCHIVO, progreso, cancelar, SHA256)


def borrar():
    shutil.rmtree(CARPETA, ignore_errors=True)


def separar(x, progreso=None, modelo=None):
    """`x`: audio estéreo (muestras, 2) en float32 a 44,1 kHz. Devuelve solo la voz, con la misma forma.
    El audio se procesa en trozos de unos 6 s que se solapan, y se descartan los bordes de cada uno."""
    import numpy as np
    import onnxruntime as ort

    sesion = ort.InferenceSession(str(modelo or ARCHIVO), providers=["CPUExecutionProvider"])
    entrada = sesion.get_inputs()[0]
    _, _, dim_f, dim_t = entrada.shape
    n_fft, salto = {2048: 6144, 3072: 7680}[dim_f], 1024
    trozo, borde = salto * (dim_t - 1), n_fft // 2
    util = trozo - 2 * borde
    ventana = np.hanning(n_fft + 1)[:-1].astype("float32")
    n = len(x)
    relleno = (-n) % util
    mezcla = np.concatenate([np.zeros((borde, 2), "float32"), x, np.zeros((relleno + borde, 2), "float32")])
    voz = np.zeros((n + relleno, 2), "float32")
    tramas_idx = np.arange(n_fft)[None, :] + salto * np.arange(dim_t)[:, None]
    peso = np.zeros(trozo + n_fft, "float32")
    for t in range(dim_t):
        peso[t * salto:t * salto + n_fft] += ventana ** 2
    for i in range(0, n + relleno, util):
        onda = np.pad(mezcla[i:i + trozo].T, ((0, 0), (borde, borde)), mode="reflect")
        espectro = np.fft.rfft(onda[:, tramas_idx] * ventana, axis=-1).transpose(0, 2, 1)[:, :dim_f, :]
        r = sesion.run(None, {entrada.name: np.stack([espectro[0].real, espectro[0].imag, espectro[1].real,
                                                      espectro[1].imag])[None].astype("float32")})[0][0]
        completo = np.zeros((2, n_fft // 2 + 1, dim_t), "complex64")
        completo[:, :dim_f] = np.stack([r[0] + 1j * r[1], r[2] + 1j * r[3]])
        tramas = np.fft.irfft(completo.transpose(0, 2, 1), n=n_fft, axis=-1) * ventana
        y = np.zeros((2, trozo + n_fft), "float32")
        for t in range(dim_t):
            y[:, t * salto:t * salto + n_fft] += tramas[:, t]
        y = (y / np.maximum(peso, 1e-8))[:, borde:borde + trozo]
        voz[i:i + util] = y[:, borde:borde + util].T
        if progreso:
            progreso(min(1.0, (i + util) / (n + relleno)))
    return voz[:n]


def voz_a_wav(audio, destino, progreso=None):
    """Decodifica cualquier audio o vídeo, aísla la voz y la guarda en `destino` (WAV mono)."""
    import numpy as np
    import soundfile as sf
    from faster_whisper.audio import decode_audio

    izq, der = decode_audio(str(audio), sampling_rate=SR, split_stereo=True)
    voz = separar(np.stack([izq, der], axis=1), progreso)
    sf.write(str(destino), voz.mean(axis=1), SR, subtype="PCM_16")
    return destino
