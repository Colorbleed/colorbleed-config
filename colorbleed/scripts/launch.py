import os
import pprint

import acre


config_root = os.path.dirname(os.path.dirname(__file__))
os.environ["TOOL_ENV"] = os.path.join(config_root, "environments")


def launch(tools, executable, args):

    tools_env = acre.get_tools(tools.split(";"))
    env = acre.compute(tools_env)

    env = acre.merge(env, current_env=dict(os.environ))
    print("Environment:\n%s" % pprint.pformat(env, indent=4))

    # Search for the executable within the tool's environment
    # by temporarily taking on its `PATH` settings
    exe = acre.which(executable, env)
    if not exe:
        raise ValueError("Unable to find executable: %s" % executable)

    print("Launching: %s" % exe)
    acre.launch(exe, environment=env, args=args, cwd=env.get("AVALON_WORKDIR"))


if __name__ == '__main__':

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--tools",
                        help="The tool environments to include. "
                             "These should be separated by `;`",
                        required=True)
    parser.add_argument("--executable",
                        help="The executable to run. ",
                        required=True)

    kwargs, args = parser.parse_known_args()

    launch(tools=kwargs.tools,
           executable=kwargs.executable,
           args=args)
