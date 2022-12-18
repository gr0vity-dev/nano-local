#!./venv_nanolocal/bin/python

import argparse
from nanolocal.nl_module import nl_runner

# * create (this will create the one time resources that need creating)
# * start (this will start the nodes)
# * init (create an initial ledger structure common to all, epoch1 and 2 and canary blocks, etc)
# * test (run tests defined in nl_config.toml testcases)
# * pytest (run tests with pytest framework)
# * stop (stop all containers)
# * stop_nodes (stop the nodes but do not destroy anything)
# * restart (restart all nodes)
# * restart_wait_sync (restart all nodes and wait for 100% confirmed blocks)
# * reset (remove all blocks except genesis blocks by deleting data.ldb)
# * destroy (destroy all autogenerated resources, so that we can start from virgin state next time)

nl_run = nl_runner()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-b',
        '--build',
        type=bool,
        default=False,
        help='build docker container for new executable             ')
    parser.add_argument(
        '--output',
        choices={"console", "html", "xml"},
        default="html",
        help=
        'create a report under ./speedsuite/testcases/reports in the specified format for each module'
    )
    parser.add_argument(
        '--loglevel',
        choices={"DEBUG", "INFO", "WARNING", "ERROR"},
        default="INFO",
        help='set log level. defaults to INFO                 ')
    parser.add_argument(
        '--args',
        default="-v -rpf",
        help='will be added after pytest. example -rfE        ')
    parser.add_argument(
        '--value',
        help=
        'tc --value "delay 100ms 20ms 50%%  loss random 0%%  corrupt 0%%  duplicate 0%%  reorder 0%%  rate 512kbit"'
    )
    parser.add_argument(
        '--nested_path',
        help='conf_edit --nested_path  "tc_enable" --value true')
    parser.add_argument(
        '--compose_version',
        type=int,
        default=2,
        choices={1, 2},
        help=
        'run $ docker-compose --version to identify the version. Defaults to 2'
    )
    parser.add_argument(
        '--runid',
        default="default",
        help='if prom-exporter is enabled, sets the run id    ')
    parser.add_argument(
        '--node',
        default="all",
        help=
        'specify for which node an action takes place. Example "start --node nl_pr1" will only start nl_pr1'
    )
    parser.add_argument(
        'command',
        help=
        'create , start, init, stop, reset, destroy, pytest, status, restart, restart_wait_sync, build_nodes, start_prom, start_prom_stack, init_wallets, tcpdump_start, tcpdump_stop',
        default='create')
    return parser.parse_args()


# #DEBUG : put def parse_args() into comment and set the command you wish to run
# def parse_args():
#     return argClass

# class argClass:
#     command = "stop"
#     compose_version = 2
#     loglevel = "INFO"
#     runid = ""


def main():

    args = parse_args()

    if args.command == "status":
        nl_run.run_command("status")
    elif args.command == 'csi':  #c(reate) s(tart) i(nit)
        nl_run.run_command("csi",
                           compose_version=args.compose_version,
                           build=args.build,
                           node="all")

    elif args.command == 'create':
        nl_run.run_command("create", compose_version=args.compose_version)

    elif args.command == 'build_nodes':
        nl_run.run_command("build_nodes", node=args.node)

    elif args.command == 'start':
        nl_run.run_command("start", build=args.build)

    elif args.command == 'start_prom':
        nl_run.run_command("start_prom", node='all')
    #  logging.getLogger().success("prom-exporter containers started")

    elif args.command == 'start_prom_stack':
        nl_run.run_command("start_prom_stack")

    elif args.command == 'init':
        nl_run.run_command("init")

    elif args.command == 'init_wallets':
        nl_run.run_command("init_wallets")

    elif args.command == 'stop':
        nl_run.run_command("stop")

    elif args.command == 'down':
        nl_run.run_command("down", node=args.node)

    elif args.command == 'stop_nodes':
        nl_run.run_command("stop_nodes", node=args.node)

    elif args.command == 'restart':
        nl_run.run_command("restart", node=args.node)

    elif args.command == 'tc':
        nl_run.run_command("tc", node=args.node, command_value=args.value)

    elif args.command == 'tc_del':
        nl_run.run_command("tc_del", node=args.node)

    elif args.command == 'restart_wait_sync':
        nl_run.run_command("restart_wait_sync")

    elif args.command == 'reset':
        nl_run.run_command("reset", node=args.node)

    elif args.command == 'destroy':
        nl_run.run_command("destroy")

    elif args.command == 'pytest':
        nl_run.run_command("pytest",
                           pytest_args=args.args,
                           pytest_output=args.output)

    elif args.command == 'tcpdump_start':
        nl_run.run_command("tcpdump_start")

    elif args.command == 'tcpdump_stop':
        nl_run.run_command("tcpdump_stop")

    elif args.command == 'test':
        nl_run.run_command("test")

    elif args.command == 'conf_edit':
        nl_run.run_command("conf_edit",
                           conf_edit_path=args.nested_path,
                           conf_edit_value=args.value)

    else:
        print(f'Unknown command {args.command}')


if __name__ == "__main__":
    main()
