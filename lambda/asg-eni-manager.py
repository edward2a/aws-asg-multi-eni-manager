import boto3
import botocore
from datetime import datetime

from eni_data import eni_limits

ec2_client = boto3.client('ec2')
asg_client = boto3.client('autoscaling')


def lambda_handler(event, context):

    if event["detail-type"] == "EC2 Instance-launch Lifecycle Action":

        instance_id = event['detail']['EC2InstanceId']
        asg_hook_name = event['detail']['LifecycleHookName']
        asg_name = event['detail']['AutoScalingGroupName']

        instance_type, subnet_id = get_instance_data(instance_id)

        interface_ids = create_interfaces(
            subnet_id, eni_limits[instance_type]['enis'])

        attachments = attach_interfaces(interface_ids, instance_id)

        if not interface_ids:
            complete_lifecycle_action_failure(
                asg_hook_name, asg_name, instance_id)

        elif not attachments:
            complete_lifecycle_action_failure(
                asg_hook_name, asg_name, instance_id)
            delete_interfaces(interface_ids)

        else:
            complete_lifecycle_action_success(
                asg_hook_name, asg_name, instance_id)


def get_instance_data(instance_id):
    """Fetch instance details and return type and subnet."""
    try:
        result = ec2_client.describe_instances(InstanceIds=[instance_id])

        vpc_subnet_id = result['Reservations'][0]['Instances'][0]['SubnetId']
        instance_type = result['Reservations'][0]['Instances'][0]['InstanceType']

        log("Subnet id: {}".format(vpc_subnet_id))
        log("Instance type: {}".format(instance_type))

    except botocore.exceptions.ClientError as e:
        log("Error describing the instance {}: {}".format(
            instance_id, e.response['Error']))

        vpc_subnet_id = None

    return instance_type, vpc_subnet_id


def create_interfaces(subnet_id, count):

    network_interface_id = None

    if subnet_id:
        try:
            network_interface = ec2_client.create_network_interface(
                SubnetId=subnet_id)
            network_interface_id = network_interface['NetworkInterface']['NetworkInterfaceId']

            log("Created network interface: {}".format(network_interface_id))

        except botocore.exceptions.ClientError as e:
            log("Error creating network interface: {}".format(e.response['Error']))

    return network_interface_id


def attach_interfaces(network_interface_id, instance_id):
    attachment = None

    if network_interface_id and instance_id:
        try:
            attach_interface = ec2_client.attach_network_interface(
                NetworkInterfaceId=network_interface_id,
                InstanceId=instance_id,
                DeviceIndex=1
            )
            attachment = attach_interface['AttachmentId']
            log("Created network attachment: {}".format(attachment))
        except botocore.exceptions.ClientError as e:
            log("Error attaching network interface: {}".format(e.response['Error']))

    return attachment


def delete_interfaces(network_interface_id):

    try:
        ec2_client.delete_network_interface(
            NetworkInterfaceId=network_interface_id)

        log("Deleted network interface: {}".format(
            network_interface_id))

        return True

    except botocore.exceptions.ClientError as e:
        log("Error deleting interface {}: {}".format(
            network_interface_id, e.response['Error']))


def complete_lifecycle_action_success(hookname, groupname, instance_id):

    try:
        asg_client.complete_lifecycle_action(
            LifecycleHookName=hookname,
            AutoScalingGroupName=groupname,
            InstanceId=instance_id,
            LifecycleActionResult='CONTINUE')

        log("Lifecycle hook CONTINUEd for: {}".format(instance_id))

    except botocore.exceptions.ClientError as e:
        log("Error completing life cycle hook for instance {}: {}".format(
            instance_id, e.response['Error']))
        log('{"Error": "1"}')


def complete_lifecycle_action_failure(hookname, groupname, instance_id):

    try:
        asg_client.complete_lifecycle_action(
                LifecycleHookName=hookname,
                AutoScalingGroupName=groupname,
                InstanceId=instance_id,
                LifecycleActionResult='ABANDON'
            )
        log("Lifecycle hook ABANDONed for: {}".format(instance_id))

    except botocore.exceptions.ClientError as e:
        log("Error completing life cycle hook for instance {}: {}".format(
            instance_id, e.response['Error']))
        log('{"Error": "1"}')


def log(error):
    print('{}Z {}'.format(datetime.utcnow().isoformat(), error))

