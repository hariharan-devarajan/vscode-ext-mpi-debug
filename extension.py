import os
import vscode
import jsonc
import shutil
import paramiko
from vscode import InfoMessage, ErrorMessage, Config
ext_mdata = vscode.ExtensionMetadata(publisher="Hariharan", license="MIT License",display_name="MPI Debug")

gdbserver_cfg = Config(name='gdbserver', description='Specifies the path of gdbserver', input_type=str, default="gdbserver")
debug_cfg = Config(name='debug_conf', description='Specifies the path of debug.conf', input_type=str, default="./debug.conf")
ext = vscode.Extension(name="MPI Debug",metadata=ext_mdata, config=[gdbserver_cfg,debug_cfg])
@ext.event
async def on_activate():
    vscode.log(f"The Extension '{ext.name}' has started")


@ext.command(category="MPI Debug", name="Attach to job")
async def attach(ctx):
    gdbserver_exe = await ctx.workspace.get_config_value(gdbserver_cfg)
    debug_conf = await ctx.workspace.get_config_value(debug_cfg)
    vscode.log(f"Reading gdbserver_exe {gdbserver_exe}")
    vscode.log(f"Reading debug_conf {debug_conf}")
    folders = await ctx.workspace.get_workspace_folders()
    app_root = str(folders[0].uri)
    vscode.log(f"Reading app_root {app_root}")
    conf_file = debug_conf
    file = open(conf_file, 'r')
    lines = file.readlines()
    file.close()
    if len(lines) == 0:
        return await ctx.show(ErrorMessage(f"Debug file {conf_file} not found."))
    else:
        total_lines = int(lines[0])
        if len(lines) - 1 != total_lines:
             return await ctx.show(ErrorMessage(f"Debug file {conf_file} does not have all lines."))
        vals = [{}]*total_lines
        for line in lines[1:]:
            if line == "":
                continue
            exec, rank, hostname, port, pid = line.split(":")
            exec = exec.strip()
            rank = int(rank.strip())
            hostname = hostname.strip()
            port = int(port.strip())
            pid = int(pid.strip())
            vals[rank] = {"hostname":hostname, "port":port, "pid":pid, "exec":exec}
        launch_file = os.path.join(app_root, ".vscode", "launch.json")
        with open(launch_file, "r") as jsonFile:
            launch_data = jsonc.load(jsonFile)
        
        # clean previous configurations
        confs = launch_data["configurations"]
        final_confs = []
        for conf in confs:
            if "mpi_gdb" not in conf["name"]:
                final_confs.append(conf)
        
        compound_names = []
        for rank, val in enumerate(vals):
            exec = val["exec"]
            port = val["port"]
            hostname = val["hostname"]
            test_name = f"mpi_gdb for rank {rank}"
            final_confs.append({
                "type": "gdb",
                "request": "attach",
                "name": test_name,
                "executable": f"{exec}",
                "target": f"{hostname}:{port}",
                "remote": True,
                "cwd": "${workspaceRoot}", 
                "gdbpath": "gdb"
            })
            compound_names.append(test_name)
        final_compounds = []
        compounds = []
        if "compounds" in launch_data:
            compounds = launch_data["compounds"]
        final_compounds = []
        for compound in compounds:
            if "mpi_gdb" not in compound["name"]:
                final_compounds.append(compound)
        
        final_compounds.append({
            "name": "mpi_gdb compound",
            "configurations": compound_names,
            "stopAll": True
        })
        launch_data["compounds"] = final_compounds


        launch_data["configurations"]=final_confs
        with open(launch_file, "w") as jsonFile:
            jsonc.dump(launch_data, jsonFile, indent=2)

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        for rank, val in enumerate(vals):
            hostname, port, pid = val["hostname"], val["port"], val["pid"]
            vscode.log(f"rank:{rank} hostname:{hostname} port:{port} pid:{pid}")
            ssh.connect(hostname)
            cmd = f"{gdbserver_exe} {hostname}:{port} --attach {pid} > {os.getcwd()}/gdbserver-{hostname}-{pid}.log 2>&1 &"
            vscode.log(f"cmd:{cmd}")
            transport = ssh.get_transport()
            channel = transport.open_session()
            channel.exec_command(cmd)
            ssh.close() 
            vscode.log(f"vals has {len(vals)} values")
            await ctx.show(InfoMessage(f"Connected {gdbserver_exe} to {hostname}:{port} --attach {pid}"))

ext.run()