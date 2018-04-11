import os

try:
    import acre
except ImportError as exc:
    raise ImportError("Module 'acre' cannot be found in the environment")


def __main__(deadlinePlugin):
    deadlinePlugin.LogInfo("Setting up studio Environment!")

    # Compute
    if "TOOL_ENV" not in os.environ:
        print("Settings TOOL_ENV ..")
        os.environ["TOOL_ENV"] = "P:/pipeline/dev/environments"

    tools = deadlinePlugin.GetProcessEnvironmentVariable("AVALON_TOOLS")
    if not tools:
        deadlinePlugin.LogInfo(
            "Cannot set studio Environment without `AVALON_TOOLS`")
        return

    deadlinePlugin.LogInfo("Setting environment for tools: %s" % tools)

    tools_env = acre.get_tools(tools.split(";"))
    env = acre.compute(tools_env)

    # Get the merged environment for the local machine
    merged = acre.merge(env, current_env=os.environ.copy())

    # Keep only the changed variables
    env = {key: value for key, value in merged.items() if key in env}

    # Update
    for key, value in sorted(env.items()):
        deadlinePlugin.LogInfo("\t%s: %s" % (key, value))
        deadlinePlugin.SetProcessEnvironmentVariable(key, value)
