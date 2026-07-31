try:
    from .script_runner import ScriptRunnerPlugin
    ScriptRunnerPlugin().register()
except Exception as e:
    import logging
    logging.exception(e)

