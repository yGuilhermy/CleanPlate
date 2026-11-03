if __name__ == '__main__':
    import json
    from pathlib import Path
    import sys
    import traceback
    try:
        from cleanplate.desktop import main
        main()
    except Exception:
        details = traceback.format_exc()
        directory = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1] / 'build'
        directory.mkdir(parents=True, exist_ok=True)
        log = directory / 'startup-error.log'
        log.write_text(details, encoding='utf-8')
        if '--verify-package' in sys.argv:
            report = Path(sys.argv[sys.argv.index('--verify-package')+1])
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps({'success':False,'error':details}), encoding='utf-8')
        else:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, 'Não foi possível iniciar o aplicativo.\n\nDetalhes em: '+str(log),
                                            'Clean Plate Studio', 0x10)
        sys.exit(1)
