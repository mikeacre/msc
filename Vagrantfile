# -*- mode: ruby -*-
# vi: set ft=ruby :

# Vagrantfile API/syntax version. Don't touch unless you know what you're doing!
VAGRANTFILE_API_VERSION = "2"

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|

  config.vm.provision :shell, path: "pg_config.sh"
  config.vm.box = "ubuntu/trusty32"
  # comment the enxt time aand uncomment the following to go public
  config.vm.network "forwarded_port", guest: 1235, host: 1235
  #config.vm.network "public_network",
  #  use_dhcp_assigned_default_route: true


end
