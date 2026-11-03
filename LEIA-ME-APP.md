# Clean Plate Studio

**Versão Alfa · Windows**

Recorte imagens e vídeos usando uma foto ou um take do cenário vazio.

## Abrir

Execute **Clean Plate Studio.exe**. Mantenha as pastas `_internal`, `bin` e `licenses` junto dele. O pacote já inclui Python, Qt e FFmpeg.

Para experimentar os controles, abra `Exemplo/exemplo.json`. O exemplo é uma figura sintética sobre um fundo fixo.

## Recortar

1. Adicione a referência em **01 Cenário vazio**.
2. Adicione o vídeo ou a imagem em **02 Vídeo original**. Também é possível arrastar arquivos para os cartões.
3. Ajuste **Tolerância** e **Transição** na aba **Recorte**. Use **Matte** para inspecionar a máscara e **Comparar** para ver original à esquerda e recorte à direita.
4. Escolha o formato na aba **Saída**. A prévia mostra o fundo selecionado.
5. Clique em **Renderizar vídeo** e escolha o arquivo de destino.

## Controles

Os sliders também aceitam valores digitados nos campos à direita. A barra de tempo permite clique, arraste e navegação por teclado quando está em foco. A reprodução da prévia não tem áudio; sua velocidade depende do processamento.

| Controle | Uso |
|---|---|
| Tolerância | Diferença necessária entre referência e frame para manter uma região |
| Transição | Faixa de transição entre fundo e objeto |
| Suavidade da borda | Desfoque aplicado à máscara |
| Expandir / contrair | Aumentar ou reduzir a área recortada |
| Refinar por cores e contornos | Corrigir o recorte inicial usando as cores do frame |
| Default, em Recorte | Restaurar sliders e checkboxes de recorte, alinhamento e limpeza |
| Default, em Efeitos | Restaurar espessuras, intensidades, deslocamentos e cor; desligar borda, sombra e glow |
| Desligar todos | Desativar os efeitos sem mudar seus valores |

**Alinhamento e limpeza** reúne os ajustes adicionais:

- **Alinhar referência automaticamente** estima posição, escala e rotação a partir do frame atual. Confira o resultado na comparação.
- **Redimensionar referência para o vídeo** serve para referências com o mesmo enquadramento. Proporções diferentes deformam a foto.
- **Estender bordas da referência** aproxima as áreas fora da foto pela cor da borda.
- **Compensar mudança global de luz** ajusta a diferença de iluminação usando superfícies claras e neutras.
- **Alcance do refino** define a região em torno do recorte inicial que pode ser corrigida. **Refino da borda** usa os detalhes RGB para ajustar o contorno; zero desliga.
- **Pequenas falhas** preenche buracos internos até a área escolhida, em pixels da resolução original. Reduza o valor para preservar vãos pequenos.
- **Preencher todos os buracos** ignora o limite de área. **Manter apenas o maior objeto** remove partes separadas. Ative essas opções apenas quando esse for o resultado desejado.

Para um take vazio, escolha início e duração da amostra e clique em **Reanalisar referência**.

## Exportar

| Saída | Arquivo | Uso |
|---|---|---|
| Transparência | MOV / ProRes 4444 | Importar o canal alpha em um editor compatível |
| Fundo sólido | MP4 / H.264 | Escolher uma cor, inclusive verde para chroma key |
| Fundo desfocado | MP4 / H.264 | Desfocar o cenário entre 0 e 100 px |
| Matte | MP4 / H.264 | Exportar a máscara em tons de cinza, sem áudio |
| Salvar frame | PNG | Salvar o frame atual na resolução original, com o modo de saída escolhido |

**Manter áudio original** vale para transparência, fundo sólido e fundo desfocado. MP4 não preserva alpha; prefira MOV quando precisar de transparência. A compressão do MP4 pode afetar detalhes finos usados no chroma key.

No fundo desfocado, zero mantém o cenário nítido. O motor usa a referência para preencher o fundo sob o objeto antes do desfoque. A intensidade fica salva no projeto e é aplicada à prévia, ao PNG e ao vídeo.

A renderização tem progresso e cancelamento. Ao fechar durante uma tarefa, o aplicativo cancela e aguarda a limpeza dos arquivos temporários.

## Projetos e atalhos

Use `Ctrl+O` para abrir mídia e `Ctrl+S` para salvar o projeto. O JSON guarda os ajustes e os caminhos dos arquivos; preserve a mídia original. Projetos das versões 1, 2 e 3 são aceitos e mantêm os ajustes salvos.

## Preparar a gravação

Use câmera fixa, cenário estático e arquivos SDR. Fotos com orientação EXIF e vídeos com rotação de 90°, 180° ou 270° são reconhecidos. Converta HDR PQ/HLG para SDR antes de importar.

Cores parecidas entre objeto e fundo, sombras e reflexos exigem ajuste. Cabelo fino, transparências e movimento borrado podem perder detalhes. Cada frame é analisado separadamente. A prévia usa resolução reduzida; confira um frame exportado antes de renderizar todo o vídeo.

## Licença

Código do projeto sob MIT. Veja `LICENSE` e `THIRD_PARTY.md`; os avisos das dependências ficam em `licenses/`.
