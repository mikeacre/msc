My Strange collection is meant to run on a vagrant box on Virtual Box

Install Virtual box
(https://www.virtualbox.org/wiki/Downloads)

Install vagrant
(https://www.vagrantup.com/downloads)

Type "vagrant --version" in terminal to ensure it is installed properly

To load the files of this program via Github utilize the GitHub console to clone
the repo:
https://github.com/mikeacre/msc

Once the files are installed on the server, move to that directory and type
"vagrant up"

This will start the server, now we must log into the vagrant server to start the program.

Type "vagrant ssh" to launch the ssh server.

Now utilize putty http://www.putty.org/ or another ssh program to log in to the 
server created. The correct port should be listed in the cmd shell.

Once inside the server navigate to the vagrant directory where  project.py is.

Run db_setup.py by entering "python db_setup.py"

Now to start the program, run "python project.py"

Ctrl-c from the ssh shell will stop the server. The port by default is set to
1235, this can be changed in the last line of project.py
