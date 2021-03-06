from aws_cdk import (
    core,
    aws_ec2 as ec2,
    aws_eks as eks,
    aws_iam as iam,
)


class CdkPythonStack(core.Stack):

    def __init__(self, scope: core.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # import default vpc
        # vpc = ec2.Vpc.from_lookup(self, id='Vpc', is_default=True)
        # from vpcId
        # vpc = ec2.Vpc.from_lookup(self, id='Vpc', vpc_id='vpc-0417e46d')
        # create vpc
        vpc = ec2.Vpc(self,
                      'eks-vpc',
                      cidr='10.3.0.0/16',
                      max_azs=3,
                      nat_gateways=1
                      )

        # create eks admin role
        eks_master_role = iam.Role(self, 'EksMasterRole',
                                   role_name='EksAdminRole',
                                   assumed_by=iam.AccountRootPrincipal()
                                   )

        cluster = eks.Cluster(self, 'Cluster',
                              vpc=vpc,
                              version=eks.KubernetesVersion.V1_18,
                              masters_role=eks_master_role,
                              default_capacity=0
                              )
        # # Conditionally dd aws console login user to the RBAC so we can browse the EKS workloads
        console_user_string = self.node.try_get_context('console_user')
        if console_user_string and 'console_user_string' in vars():
            console_user = iam.User.from_user_name(self, 'ConsoleUser', user_name=console_user_string)
            cluster.aws_auth.add_user_mapping(console_user, groups=['system:masters'])

        # user data
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            'set -o xtrace',
            '/etc/eks/bootstrap.sh {}'.format('cluster.clusterName')
        )
        lt = ec2.CfnLaunchTemplate(self, 'LT',
                                   launch_template_data={
                                       'imageId': eks.EksOptimizedImage().get_image(self).image_id,
                                       'instanceType': ec2.InstanceType('t3.large'). to_string(),
                                       'user_data': core.Fn.base64(user_data.render()),
                                       'tagSpecifications': [
                                           {
                                               'resourceType': 'instance',
                                               'tags': [
                                                   {'key': 'Name', 'value': 'MNG'},
                                                   {'key': 'Foo', 'value': 'Bar'}
                                               ]
                                           }
                                       ]
                                   }
                                   )
        # create eks managed nodegroup
        cluster.add_nodegroup_capacity('MNG',
                                       launch_template_spec={
                                           'id': lt.ref,
                                           'version': lt.attr_default_version_number,
                                       },
                                       desired_size=2
                                       )

        # # create self-managed nodegroup with ASG
        # asgng = cluster.add_auto_scaling_group_capacity('ASGNG',
        #                                                 instance_type=ec2.InstanceType('t3.large'),
        #                                                 desired_capacity=2)

        # core.Tags.of(asgng).add('Name', 'self-managed-ng',
        #                         apply_to_launched_instances=True
        #                         )

        # core.CfnOutput(self, 'EksMasterRoleArn', value=eks_master_role.role_arn)
