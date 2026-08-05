try:
    # pyrefly: ignore [missing-import]
    from .Autoplacer.script_runner import ScriptRunnerPlugin
    ScriptRunnerPlugin().register()
except Exception as e:
    import logging
    logging.exception(e)
