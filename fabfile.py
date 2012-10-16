import time
import boto
from fabric.api import *

# replace this with your key pair name
KEY='Main'

# micro instance with Ubuntu 12.04 in us-east-1
AMI = 'ami-3d4ff254'

def start_instance():
    """ start micro instance and add it to host list """
    # assume that boto is already configured
    c = boto.connect_ec2()
    reservation = c.run_instances(AMI, instance_type='t1.micro', key_name=KEY)
    instance = reservation.instances[0]
    print('Waiting for instance to start...')
    status = instance.update()
    while status == 'pending':
        time.sleep(10)
        status = instance.update()

    if status == 'running':
        print('New instance "' + instance.id + '" accessible at ' + instance.public_dns_name)
    else:
        print('Instance status: ' + status)
        return

    return instance

def install_packages():
    """ install required software """
    with hide('stdout'):
        sudo('apt-get -qq -y update')
        sudo('apt-get -qq -y dist-upgrade')
        sudo('apt-get -qq -y install python-virtualenv')
        sudo('apt-get -qq -y install apache2')
        sudo('apt-get -qq -y install libapache2-mod-wsgi')
    
def create_user():
    """ create a user account for the django app """
    sudo('useradd -m django')

def create_virtualenv():
    """ create a virtual environment for django vhost """
    with cd('/var'):
        sudo('virtualenv --no-site-packages -q django')
    with cd('/var/django'):
        with prefix('source ./bin/activate'):
            sudo('chown -R ubuntu:ubuntu /var/django')
            run('pip install Django')
            run('pip install boto')
            run('django-admin.py startproject website')

def configure_django():
    put('files/wsgi.py', '/var/django/website')
    put('files/django', '/etc/apache2/sites-available', use_sudo=True)
    sudo('a2ensite django')
    sudo('a2dissite default')
    sudo('service apache2 restart')
    sudo('chown -R django:django /var/django')

def configure_boto():
    """ create a global boto config file """
    key = boto.config.get_value('Credentials', 'aws_access_key_id')
    secret = boto.config.get_value('Credentials', 'aws_secret_access_key')
    config = """
[Credentials]
aws_access_key_id = %s
aws_secret_access_key = %s
"""
    sudo('echo "' + config % (key, secret) + '" > /etc/boto.conf', shell=True)

def terminate_instance(instance):
    """ terminate a running instance """
    # assume that boto is already configured
    c = boto.connect_ec2()
    c.terminate_instances(instance_ids=[instance.id,])

    print('Waiting for instance to terminate...')
    status = instance.update()
    while status == 'shutting-down':
        time.sleep(10)
        status = instance.update()

    if status == 'terminated':
        print('Instance "' + instance.id + '" is terminated')
    else:
        print('Instance status: ' + status)
        return
    
@task(default=True)
def setup_server():
    instance = start_instance()

    # disable known_hosts checking, since we are starting a new server
    env.disable_known_hosts = True
    # set host string to our new instance
    env.host_string = instance.public_dns_name

    env.connection_attempts = 5
    env.timeout = 30

    # set SSH key and username
    env.user = 'ubuntu'
    env.key_filename = '~/.ssh/aws.pem'

    install_packages()
    create_user()
    create_virtualenv()
    configure_django()
    configure_boto()
    #terminate_instance(instance)
