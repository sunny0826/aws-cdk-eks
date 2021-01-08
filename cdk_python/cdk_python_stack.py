from aws_cdk import (
    core,
    aws_ec2 as ec2,
    aws_eks as eks,
)


class CdkPythonStack(core.Stack):

    def __init__(self, scope: core.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # import default vpc
        # vpc = ec2.Vpc.from_lookup(self, id='Vpc', is_default=True)
        # from vpcId
        vpc = ec2.Vpc.from_lookup(self, id='Vpc', vpc_id='vpc-0417e46d')

        cluster = eks.Cluster(self, 'Cluster',
                              vpc=vpc,
                              version=eks.KubernetesVersion.V1_18,
                              default_capacity=0
                              )

        cluster.add_nodegroup_capacity('MNG',
                                       capacity_type=eks.CapacityType.SPOT,
                                       desired_size=2,
                                       instance_types=[
                                           ec2.InstanceType('t3.large'),
                                           ec2.InstanceType('m5.large'),
                                           ec2.InstanceType('c5.large'),
                                       ]),
        asgng = cluster.add_auto_scaling_group_capacity('ASGNG',
                                                        instance_type=ec2.InstanceType('t3.large'),
                                                        desired_capacity=2)

        core.Tags.of(asgng).add('Name', 'self-managed-ng',
                                apply_to_launched_instances=True
                                )
