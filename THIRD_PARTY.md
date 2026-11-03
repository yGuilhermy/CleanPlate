# Dependências

A licença MIT do Clean Plate Studio cobre o código e os assets próprios do projeto. Ela não substitui as licenças das bibliotecas ou dos executáveis incluídos nos pacotes.

Os scripts de build copiam os avisos encontrados nas distribuições Python para `licenses/`. Os arquivos de dependências em `requirements*.txt` definem os componentes usados pelo aplicativo e pelo terminal.

| Componente | Referência |
|---|---|
| Python | [Licença e histórico](https://docs.python.org/3/license.html) |
| Qt / PySide6 / Shiboken6 | [Licenças do Qt for Python](https://doc.qt.io/qtforpython-6/licenses.html) |
| NumPy | [Licença](https://numpy.org/doc/stable/license.html) |
| Pillow | [Licença](https://pillow.readthedocs.io/en/stable/about.html#license) |
| OpenCV e bibliotecas do wheel | [Avisos do opencv-python](https://github.com/opencv/opencv-python#licensing) |
| SDK MCP | [Licença](https://github.com/modelcontextprotocol/python-sdk/blob/main/LICENSE) |
| PyInstaller e bootloader | [Licença e exceção de distribuição](https://pyinstaller.org/en/stable/license.html) |
| FFmpeg / FFprobe | [Licenças e distribuição](https://ffmpeg.org/legal.html) |

## FFmpeg

O build copia `ffmpeg` e `ffprobe` encontrados no PATH e registra versão, configuração e hashes em `licenses/runtime.json`. Eles são executados como processos separados. A licença depende das opções e bibliotecas da compilação escolhida; não presuma que qualquer binário seja LGPL.

A compilação Gyan 7.1.1 usada no desenvolvimento habilita `--enable-gpl` e `--enable-version3`. Sua origem é [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/). Para distribuir um pacote, preserve os avisos e forneça o código-fonte correspondente aos binários e às bibliotecas incluídas, nos termos das licenças aplicáveis. A pasta `licenses/` e o manifesto de runtime identificam os componentes; não substituem esse código-fonte.
