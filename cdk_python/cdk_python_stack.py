from aws_cdk import (
    core,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_eks as eks,
)


class CdkPythonStack(core.Stack):

    def __init__(self, scope: core.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 使用现有 Vpc
        # vpc = ec2.Vpc.from_lookup(self, 'office', vpc_id='vpc-bbf45ad2')
        # 新建 Vpc 跨 3 az 一个 nat
        vpc = ec2.Vpc(self, 'eks-vpc',
                      cidr='10.3.0.0/16',
                      max_azs=3,
                      nat_gateways=1
                      )

        eks_sg = ec2.SecurityGroup(self, 'eks-security-group',
                                   vpc=vpc,
                                   allow_all_outbound=True,
                                   description='CDK Security Group'
                                   )

        # 需要使用 account_id=self.account，否则将无法操作 eks
        cluster_admin = iam.Role(self, "AdminRole",
                                 assumed_by=iam.AccountPrincipal(
                                     account_id=self.account)
                                 )

        cluster = eks.Cluster(self, 'Cluster',
                              version=eks.KubernetesVersion.V1_16,
                              cluster_name='eks-test',
                              vpc=vpc,
                              vpc_subnets=[ec2.SubnetSelection(
                                  one_per_az=True, subnet_type=ec2.SubnetType.PRIVATE)],
                              default_capacity=0,
                              default_capacity_instance=ec2.InstanceType(
                                  'm5.large'),
                              masters_role=cluster_admin,
                              output_cluster_name=True,
                              security_group=eks_sg,
                              )

        cluster.add_nodegroup_capacity("node-group",
                                       instance_type=ec2.InstanceType(
                                           "m5.large"),
                                       desired_size=1,
                                       nodegroup_name="eks-node",
                                       max_size=4,
                                       min_size=1,
                                       tags={"dep": "tech", "team": "ops",
                                             "env": "dev", "proj": "eks-test"}
                                       )

        # add instance nodes
        # asg = cluster.add_auto_scaling_group_capacity(
        #     "auto-scaling-group",
        #     instance_type=ec2.InstanceType(
        #         "m5.large"),
        #     desired_capacity=3,
        #     max_capacity=4,
        #     min_capacity=1,
        # )

        # asg.add_security_group(security_group=eks_sg)

        core.CfnOutput(self, 'Region', value=self.region)
        core.CfnOutput(self, 'VpcId', value=vpc.vpc_id)

        # The code that defines your stack goes here
