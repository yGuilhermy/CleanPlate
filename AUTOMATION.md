# Terminal e MCP

**Versão Alfa · CLI e MCP por stdio**

O terminal e o MCP usam o motor do aplicativo sem carregar a interface Qt. Os projetos JSON são compatíveis com a interface gráfica.

## Terminal

No pacote compilado, execute `CleanPlateControl.exe --help`. Mantenha `_internal`, `bin` e `licenses` junto do executável. Na árvore do projeto, `cleanplate.cmd` procura o pacote e depois o Python de `.venv` ou do PATH.

No código-fonte:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-automation.txt
.\.venv\Scripts\python.exe -m cleanplate --help
.\.venv\Scripts\python.exe -m cleanplate preview demo/projeto.json output/previa.png
```

A [referência dos comandos](skills/cleanplate-control/references/commands.md) contém exemplos, parâmetros, modos de saída, resultados JSON e cancelamento.

O stdout contém um resultado JSON por chamada. Progresso de renderização vai para stderr. `Ctrl+C` solicita cancelamento de uma renderização síncrona; os comandos `job-*` controlam tarefas em segundo plano.

## MCP por stdio

O cliente MCP deve iniciar este comando como subprocesso:

```powershell
CleanPlateControl.exe mcp --jobs-dir ./.cleanplate-jobs
```

Para usar o código-fonte, execute `.\.venv\Scripts\python.exe -m cleanplate mcp --jobs-dir ./.cleanplate-jobs` a partir da pasta do projeto. Na configuração do cliente, use o caminho completo do Python e de `tools/control_entry.py` para não depender da pasta de trabalho do host.

O arquivo [mcp.example.json](mcp.example.json) mostra o formato de configuração de clientes que aceitam `mcpServers`. Substitua `command` pelo caminho do executável na sua instalação, ou coloque sua pasta no PATH. Escolha uma pasta de jobs gravável. A configuração é um exemplo; não registra o servidor automaticamente.

O servidor expõe 12 ferramentas para consultar mídia e parâmetros, criar/editar projetos, alinhar, gerar prévias e frames e controlar jobs. A prévia retorna uma imagem junto dos dados estruturados. O transporte usa o [SDK MCP por stdio](https://py.sdk.modelcontextprotocol.io/run/).

Mantenha a conexão aberta durante a renderização: alguns hosts encerram processos filhos ao desconectar. Resultados concluídos e histórico continuam consultáveis pela pasta de jobs. Se o worker for encerrado, seu PID é detectado e o status passa para falha; encerramentos forçados podem deixar parciais ou locks para inspeção.

## Skill

A pasta [skills/cleanplate-control](skills/cleanplate-control/SKILL.md) contém a skill e sua referência de comandos. Uma cópia acompanha o pacote de terminal. Ela pode ser lida diretamente ou instalada separadamente pelo usuário; o aplicativo não a instala.

## Build

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe tools/build_control.py
```

O build exige Windows e FFmpeg/FFprobe no PATH. O resultado fica em `dist/CleanPlateControl/`.

## Licença

Código do projeto sob [MIT](LICENSE). As dependências mantêm suas [licenças próprias](THIRD_PARTY.md).
