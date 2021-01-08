"""
# Amazon EKS Construct Library

<!--BEGIN STABILITY BANNER-->---


![cfn-resources: Stable](https://img.shields.io/badge/cfn--resources-stable-success.svg?style=for-the-badge)

> All classes with the `Cfn` prefix in this module ([CFN Resources](https://docs.aws.amazon.com/cdk/latest/guide/constructs.html#constructs_lib)) are always stable and safe to use.

![cdk-constructs: Developer Preview](https://img.shields.io/badge/cdk--constructs-developer--preview-informational.svg?style=for-the-badge)

> The APIs of higher level constructs in this module are in **developer preview** before they
> become stable. We will only make breaking changes to address unforeseen API issues. Therefore,
> these APIs are not subject to [Semantic Versioning](https://semver.org/), and breaking changes
> will be announced in release notes. This means that while you may use them, you may need to
> update your source code when upgrading to a newer version of this package.

---
<!--END STABILITY BANNER-->

This construct library allows you to define [Amazon Elastic Container Service for Kubernetes (EKS)](https://aws.amazon.com/eks/) clusters.
In addition, the library also supports defining Kubernetes resource manifests within EKS clusters.

## Table Of Contents

* [Quick Start](#quick-start)
* [API Reference](https://docs.aws.amazon.com/cdk/api/latest/docs/aws-eks-readme.html)
* [Architectural Overview](#architectural-overview)
* [Provisioning clusters](#provisioning-clusters)

  * [Managed node groups](#managed-node-groups)
  * [Fargate Profiles](#fargate-profiles)
  * [Self-managed nodes](#self-managed-nodes)
  * [Endpoint Access](#endpoint-access)
  * [VPC Support](#vpc-support)
  * [Kubectl Support](#kubectl-support)
  * [ARM64 Support](#arm64-support)
  * [Masters Role](#masters-role)
  * [Encryption](#encryption)
* [Permissions and Security](#permissions-and-security)
* [Applying Kubernetes Resources](#applying-kubernetes-resources)

  * [Kubernetes Manifests](#kubernetes-manifests)
  * [Helm Charts](#helm-charts)
  * [CDK8s Charts](#cdk8s-charts)
* [Patching Kuberentes Resources](#patching-kubernetes-resources)
* [Querying Kubernetes Resources](#querying-kubernetes-resources)
* [Using existing clusters](#using-existing-clusters)
* [Known Issues and Limitations](#known-issues-and-limitations)

## Quick Start

This example defines an Amazon EKS cluster with the following configuration:

* Dedicated VPC with default configuration (Implicitly created using [ec2.Vpc](https://docs.aws.amazon.com/cdk/api/latest/docs/aws-ec2-readme.html#vpc))
* A Kubernetes pod with a container based on the [paulbouwer/hello-kubernetes](https://github.com/paulbouwer/hello-kubernetes) image.

```python
# Example automatically generated. See https://github.com/aws/jsii/issues/826
# provisiong a cluster
cluster = eks.Cluster(self, "hello-eks",
    version=eks.KubernetesVersion.V1_18
)

# apply a kubernetes manifest to the cluster
cluster.add_manifest("mypod", {
    "api_version": "v1",
    "kind": "Pod",
    "metadata": {"name": "mypod"},
    "spec": {
        "containers": [{
            "name": "hello",
            "image": "paulbouwer/hello-kubernetes:1.5",
            "ports": [{"container_port": 8080}]
        }
        ]
    }
})
```

In order to interact with your cluster through `kubectl`, you can use the `aws eks update-kubeconfig` [AWS CLI command](https://docs.aws.amazon.com/cli/latest/reference/eks/update-kubeconfig.html)
to configure your local kubeconfig. The EKS module will define a CloudFormation output in your stack which contains the command to run. For example:

```plaintext
Outputs:
ClusterConfigCommand43AAE40F = aws eks update-kubeconfig --name cluster-xxxxx --role-arn arn:aws:iam::112233445566:role/yyyyy
```

Execute the `aws eks update-kubeconfig ...` command in your terminal to create or update a local kubeconfig context:

```console
$ aws eks update-kubeconfig --name cluster-xxxxx --role-arn arn:aws:iam::112233445566:role/yyyyy
Added new context arn:aws:eks:rrrrr:112233445566:cluster/cluster-xxxxx to /home/boom/.kube/config
```

And now you can simply use `kubectl`:

```console
$ kubectl get all -n kube-system
NAME                           READY   STATUS    RESTARTS   AGE
pod/aws-node-fpmwv             1/1     Running   0          21m
pod/aws-node-m9htf             1/1     Running   0          21m
pod/coredns-5cb4fb54c7-q222j   1/1     Running   0          23m
pod/coredns-5cb4fb54c7-v9nxx   1/1     Running   0          23m
...
```

## Architectural Overview

The following is a qualitative diagram of the various possible components involved in the cluster deployment.

```text
 +-----------------------------------------------+               +-----------------+
 |                 EKS Cluster                   |    kubectl    |                 |
 |-----------------------------------------------|<-------------+| Kubectl Handler |
 |                                               |               |                 |
 |                                               |               +-----------------+
 | +--------------------+    +-----------------+ |
 | |                    |    |                 | |
 | | Managed Node Group |    | Fargate Profile | |               +-----------------+
 | |                    |    |                 | |               |                 |
 | +--------------------+    +-----------------+ |               | Cluster Handler |
 |                                               |               |                 |
 +-----------------------------------------------+               +-----------------+
    ^                                   ^                          +
    |                                   |                          |
    | connect self managed capacity     |                          | aws-sdk
    |                                   | create/update/delete     |
    +                                   |                          v
 +--------------------+                 +              +-------------------+
 |                    |                 --------------+| eks.amazonaws.com |
 | Auto Scaling Group |                                +-------------------+
 |                    |
 +--------------------+
```

In a nutshell:

* `EKS Cluster` - The cluster endpoint created by EKS.
* `Managed Node Group` - EC2 worker nodes managed by EKS.
* `Fargate Profile` - Fargate worker nodes managed by EKS.
* `Auto Scaling Group` - EC2 worker nodes managed by the user.
* `KubectlHandler` - Lambda function for invoking `kubectl` commands on the cluster - created by CDK.
* `ClusterHandler` - Lambda function for interacting with EKS API to manage the cluster lifecycle - created by CDK.

A more detailed breakdown of each is provided further down this README.

## Provisioning clusters

Creating a new cluster is done using the `Cluster` or `FargateCluster` constructs. The only required property is the kubernetes `version`.

```python
# Example automatically generated. See https://github.com/aws/jsii/issues/826
eks.Cluster(self, "HelloEKS",
    version=eks.KubernetesVersion.V1_18
)
```

You can also use `FargateCluster` to provision a cluster that uses only fargate workers.

```python
# Example automatically generated. See https://github.com/aws/jsii/issues/826
eks.FargateCluster(self, "HelloEKS",
    version=eks.KubernetesVersion.V1_18
)
```

> **NOTE: Only 1 cluster per stack is supported.** If you have a use-case for multiple clusters per stack, or would like to understand more about this limitation, see [https://github.com/aws/aws-cdk/issues/10073](https://github.com/aws/aws-cdk/issues/10073).

Below you'll find a few important cluster configuration options. First of which is Capacity.
Capacity is the amount and the type of worker nodes that are available to the cluster for deploying resources. Amazon EKS offers 3 ways of configuring capacity, which you can combine as you like:

### Managed node groups

Amazon EKS managed node groups automate the provisioning and lifecycle management of nodes (Amazon EC2 instances) for Amazon EKS Kubernetes clusters.
With Amazon EKS managed node groups, you don’t need to separately provision or register the Amazon EC2 instances that provide compute capacity to run your Kubernetes applications. You can create, update, or terminate nodes for your cluster with a single operation. Nodes run using the latest Amazon EKS optimized AMIs in your AWS account while node updates and terminations gracefully drain nodes to ensure that your applications stay available.

> For more details visit [Amazon EKS Managed Node Groups](https://docs.aws.amazon.com/eks/latest/userguide/managed-node-groups.html).

**Managed Node Groups are the recommended way to allocate cluster capacity.**

By default, this library will allocate a managed node group with 2 *m5.large* instances (this instance type suits most common use-cases, and is good value for money).

At cluster instantiation time, you can customize the number of instances and their type:

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
eks.Cluster(self, "HelloEKS",
    version=eks.KubernetesVersion.V1_18,
    default_capacity=5,
    default_capacity_instance=ec2.InstanceType.of(ec2.InstanceClass.M5, ec2.InstanceSize.SMALL)
)
```

To access the node group that was created on your behalf, you can use `cluster.defaultNodegroup`.

Additional customizations are available post instantiation. To apply them, set the default capacity to 0, and use the `cluster.addNodegroupCapacity` method:

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
cluster = eks.Cluster(self, "HelloEKS",
    version=eks.KubernetesVersion.V1_18,
    default_capacity=0
)

cluster.add_nodegroup_capacity("custom-node-group",
    instance_type=ec2.InstanceType("m5.large"),
    min_size=4,
    disk_size=100,
    ami_type=eks.NodegroupAmiType.AL2_X86_64_GPU, ...
)
```

#### Launch Template Support

You can specify a launch template that the node group will use. Note that when using a custom AMI, Amazon EKS doesn't merge any user data.
Rather, You are responsible for supplying the required bootstrap commands for nodes to join the cluster.
In the following example, `/ect/eks/bootstrap.sh` from the AMI will be used to bootstrap the node.

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
user_data = ec2.UserData.for_linux()
user_data.add_commands("set -o xtrace", f"/etc/eks/bootstrap.sh {cluster.clusterName}")
lt = ec2.CfnLaunchTemplate(self, "LaunchTemplate",
    launch_template_data={
        "image_id": "some-ami-id", # custom AMI
        "instance_type": ec2.InstanceType("t3.small").to_string(),
        "user_data": Fn.base64(user_data.render())
    }
)
cluster.add_nodegroup_capacity("extra-ng",
    launch_template_spec={
        "id": lt.ref,
        "version": lt.attr_default_version_number
    }
)
```

> For more details visit [Launch Template Support](https://docs.aws.amazon.com/en_ca/eks/latest/userguide/launch-templates.html).

Graviton 2 instance types are supported including `c6g`, `m6g`, `r6g` and `t4g`.

### Fargate profiles

AWS Fargate is a technology that provides on-demand, right-sized compute
capacity for containers. With AWS Fargate, you no longer have to provision,
configure, or scale groups of virtual machines to run containers. This removes
the need to choose server types, decide when to scale your node groups, or
optimize cluster packing.

You can control which pods start on Fargate and how they run with Fargate
Profiles, which are defined as part of your Amazon EKS cluster.

See [Fargate Considerations](https://docs.aws.amazon.com/eks/latest/userguide/fargate.html#fargate-considerations) in the AWS EKS User Guide.

You can add Fargate Profiles to any EKS cluster defined in your CDK app
through the `addFargateProfile()` method. The following example adds a profile
that will match all pods from the "default" namespace:

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
cluster.add_fargate_profile("MyProfile",
    selectors=[{"namespace": "default"}]
)
```

You can also directly use the `FargateProfile` construct to create profiles under different scopes:

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
eks.FargateProfile(scope, "MyProfile",
    cluster=cluster, ...
)
```

To create an EKS cluster that **only** uses Fargate capacity, you can use `FargateCluster`.
The following code defines an Amazon EKS cluster with a default Fargate Profile that matches all pods from the "kube-system" and "default" namespaces. It is also configured to [run CoreDNS on Fargate](https://docs.aws.amazon.com/eks/latest/userguide/fargate-getting-started.html#fargate-gs-coredns).

```python
# Example automatically generated. See https://github.com/aws/jsii/issues/826
cluster = eks.FargateCluster(self, "MyCluster",
    version=eks.KubernetesVersion.V1_18
)
```

**NOTE**: Classic Load Balancers and Network Load Balancers are not supported on
pods running on Fargate. For ingress, we recommend that you use the [ALB Ingress
Controller](https://docs.aws.amazon.com/eks/latest/userguide/alb-ingress.html)
on Amazon EKS (minimum version v1.1.4).

### Self-managed nodes

Another way of allocating capacity to an EKS cluster is by using self-managed nodes.
EC2 instances that are part of the auto-scaling group will serve as worker nodes for the cluster.
This type of capacity is also commonly referred to as *EC2 Capacity** or *EC2 Nodes*.

For a detailed overview please visit [Self Managed Nodes](https://docs.aws.amazon.com/eks/latest/userguide/worker.html).

Creating an auto-scaling group and connecting it to the cluster is done using the `cluster.addAutoScalingGroupCapacity` method:

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
cluster.add_auto_scaling_group_capacity("frontend-nodes",
    instance_type=ec2.InstanceType("t2.medium"),
    min_capacity=3,
    vpc_subnets={"subnet_type": ec2.SubnetType.PUBLIC}
)
```

To connect an already initialized auto-scaling group, use the `cluster.connectAutoScalingGroupCapacity()` method:

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
asg = ec2.AutoScalingGroup(...)
cluster.connect_auto_scaling_group_capacity(asg)
```

In both cases, the [cluster security group](https://docs.aws.amazon.com/eks/latest/userguide/sec-group-reqs.html#cluster-sg) will be autoamtically attached to
the auto-scaling group, allowing for traffic to flow freely between managed and self-managed nodes.

> **Note:** The default `updateType` for auto-scaling groups does not replace existing nodes. Since security groups are determined at launch time, self-managed nodes that were provisioned with version `1.78.0` or lower, will not be updated.
> To apply the new configuration on all your self-managed nodes, you'll need to replace the nodes using the `UpdateType.REPLACING_UPDATE` policy for the [`updateType`](https://docs.aws.amazon.com/cdk/api/latest/docs/@aws-cdk_aws-autoscaling.AutoScalingGroup.html#updatetypespan-classapi-icon-api-icon-deprecated-titlethis-api-element-is-deprecated-its-use-is-not-recommended%EF%B8%8Fspan) property.

You can customize the [/etc/eks/boostrap.sh](https://github.com/awslabs/amazon-eks-ami/blob/master/files/bootstrap.sh) script, which is responsible
for bootstrapping the node to the EKS cluster. For example, you can use `kubeletExtraArgs` to add custom node labels or taints.

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
cluster.add_auto_scaling_group_capacity("spot",
    instance_type=ec2.InstanceType("t3.large"),
    min_capacity=2,
    bootstrap_options={
        "kubelet_extra_args": "--node-labels foo=bar,goo=far",
        "aws_api_retry_attempts": 5
    }
)
```

To disable bootstrapping altogether (i.e. to fully customize user-data), set `bootstrapEnabled` to `false`.
You can also configure the cluster to use an auto-scaling group as the default capacity:

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
cluster = eks.Cluster(self, "HelloEKS",
    version=eks.KubernetesVersion.V1_18,
    default_capacity_type=eks.DefaultCapacityType.EC2
)
```

This will allocate an auto-scaling group with 2 *m5.large* instances (this instance type suits most common use-cases, and is good value for money).
To access the `AutoScalingGroup` that was created on your behalf, you can use `cluster.defaultCapacity`.
You can also independently create an `AutoScalingGroup` and connect it to the cluster using the `cluster.connectAutoScalingGroupCapacity` method:

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
asg = ec2.AutoScalingGroup(...)
cluster.connect_auto_scaling_group_capacity(asg)
```

This will add the necessary user-data and configure all connections, roles, and tags needed for the instances in the auto-scaling group to properly join the cluster.

#### Spot Instances

When using self-managed nodes, you can configure the capacity to use spot instances, greatly reducing capacity cost.
To enable spot capacity, use the `spotPrice` property:

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
cluster.add_auto_scaling_group_capacity("spot",
    spot_price="0.1094",
    instance_type=ec2.InstanceType("t3.large"),
    max_capacity=10
)
```

> Spot instance nodes will be labeled with `lifecycle=Ec2Spot` and tainted with `PreferNoSchedule`.

The [AWS Node Termination Handler](https://github.com/aws/aws-node-termination-handler) `DaemonSet` will be
installed from [Amazon EKS Helm chart repository](https://github.com/aws/eks-charts/tree/master/stable/aws-node-termination-handler) on these nodes.
The termination handler ensures that the Kubernetes control plane responds appropriately to events that
can cause your EC2 instance to become unavailable, such as [EC2 maintenance events](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/monitoring-instances-status-check_sched.html)
and [EC2 Spot interruptions](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/spot-interruptions.html) and helps gracefully stop all pods running on spot nodes that are about to be
terminated.

> Handler Version: [1.7.0](https://github.com/aws/aws-node-termination-handler/releases/tag/v1.7.0)
>
> Chart Version: [0.9.5](https://github.com/aws/eks-charts/blob/v0.0.28/stable/aws-node-termination-handler/Chart.yaml)

#### Bottlerocket

[Bottlerocket](https://aws.amazon.com/bottlerocket/) is a Linux-based open-source operating system that is purpose-built by Amazon Web Services for running containers on virtual machines or bare metal hosts.
At this moment, `Bottlerocket` is only supported when using self-managed auto-scaling groups.

> **NOTICE**: Bottlerocket is only available in [some supported AWS regions](https://github.com/bottlerocket-os/bottlerocket/blob/develop/QUICKSTART-EKS.md#finding-an-ami).

The following example will create an auto-scaling group of 2 `t3.small` Linux instances running with the `Bottlerocket` AMI.

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
cluster.add_auto_scaling_group_capacity("BottlerocketNodes",
    instance_type=ec2.InstanceType("t3.small"),
    min_capacity=2,
    machine_image_type=eks.MachineImageType.BOTTLEROCKET
)
```

The specific Bottlerocket AMI variant will be auto selected according to the k8s version for the `x86_64` architecture.
For example, if the Amazon EKS cluster version is `1.17`, the Bottlerocket AMI variant will be auto selected as
`aws-k8s-1.17` behind the scene.

> See [Variants](https://github.com/bottlerocket-os/bottlerocket/blob/develop/README.md#variants) for more details.

Please note Bottlerocket does not allow to customize bootstrap options and `bootstrapOptions` properties is not supported when you create the `Bottlerocket` capacity.

### Endpoint Access

When you create a new cluster, Amazon EKS creates an endpoint for the managed Kubernetes API server that you use to communicate with your cluster (using Kubernetes management tools such as `kubectl`)

By default, this API server endpoint is public to the internet, and access to the API server is secured using a combination of
AWS Identity and Access Management (IAM) and native Kubernetes [Role Based Access Control](https://kubernetes.io/docs/reference/access-authn-authz/rbac/) (RBAC).

You can configure the [cluster endpoint access](https://docs.aws.amazon.com/eks/latest/userguide/cluster-endpoint.html) by using the `endpointAccess` property:

```python
# Example automatically generated. See https://github.com/aws/jsii/issues/826
cluster = eks.Cluster(self, "hello-eks",
    version=eks.KubernetesVersion.V1_18,
    endpoint_access=eks.EndpointAccess.PRIVATE
)
```

### VPC Support

You can specify the VPC of the cluster using the `vpc` and `vpcSubnets` properties:

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
vpc = ec2.Vpc(self, "Vpc")

eks.Cluster(self, "HelloEKS",
    version=eks.KubernetesVersion.V1_18,
    vpc=vpc,
    vpc_subnets=[SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE)]
)
```

> Note: Isolated VPCs (i.e with no internet access) are not currently supported. See https://github.com/aws/aws-cdk/issues/12171

If you do not specify a VPC, one will be created on your behalf, which you can then access via `cluster.vpc`. The cluster VPC will be associated to any EKS managed capacity (i.e Managed Node Groups and Fargate Profiles).

If you allocate self managed capacity, you can specify which subnets should the auto-scaling group use:

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
vpc = ec2.Vpc(self, "Vpc")
cluster.add_auto_scaling_group_capacity("nodes",
    vpc_subnets={"subnets": vpc.private_subnets}
)
```

There are two additional components you might want to provision within the VPC.

#### Kubectl Handler

The `KubectlHandler` is a Lambda function responsible to issuing `kubectl` and `helm` commands against the cluster when you add resource manifests to the cluster.

The handler association to the VPC is derived from the `endpointAccess` configuration. The rule of thumb is: *If the cluster VPC can be associated, it will be*.

Breaking this down, it means that if the endpoint exposes private access (via `EndpointAccess.PRIVATE` or `EndpointAccess.PUBLIC_AND_PRIVATE`), and the VPC contains **private** subnets, the Lambda function will be provisioned inside the VPC and use the private subnets to interact with the cluster. This is the common use-case.

If the endpoint does not expose private access (via `EndpointAccess.PUBLIC`) **or** the VPC does not contain private subnets, the function will not be provisioned within the VPC.

#### Cluster Handler

The `ClusterHandler` is a Lambda function responsible to interact with the EKS API in order to control the cluster lifecycle. To provision this function inside the VPC, set the `placeClusterHandlerInVpc` property to `true`. This will place the function inside the private subnets of the VPC based on the selection strategy specified in the [`vpcSubnets`](https://docs.aws.amazon.com/cdk/api/latest/docs/@aws-cdk_aws-eks.Cluster.html#vpcsubnetsspan-classapi-icon-api-icon-experimental-titlethis-api-element-is-experimental-it-may-change-without-noticespan) property.

You can configure the environment of this function by specifying it at cluster instantiation. For example, this can be useful in order to configure an http proxy:

```python
# Example automatically generated. See https://github.com/aws/jsii/issues/826
cluster = eks.Cluster(self, "hello-eks",
    version=eks.KubernetesVersion.V1_18,
    cluster_handler_environment={
        "http_proxy": "http://proxy.myproxy.com"
    }
)
```

### Kubectl Support

The resources are created in the cluster by running `kubectl apply` from a python lambda function.

#### Environment

You can configure the environment of this function by specifying it at cluster instantiation. For example, this can be useful in order to configure an http proxy:

```python
# Example automatically generated. See https://github.com/aws/jsii/issues/826
cluster = eks.Cluster(self, "hello-eks",
    version=eks.KubernetesVersion.V1_18,
    kubectl_environment={
        "http_proxy": "http://proxy.myproxy.com"
    }
)
```

#### Runtime

By default, the `kubectl`, `helm` and `aws` commands used to operate the cluster are provided by an AWS Lambda Layer from the AWS Serverless Application in [aws-lambda-layer-kubectl](https://github.com/aws-samples/aws-lambda-layer-kubectl). In most cases this should be sufficient.

You can provide a custom layer in case the default layer does not meet your
needs or if the SAR app is not available in your region.

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
# custom build:
layer = lambda_.LayerVersion(self, "KubectlLayer",
    code=lambda_.Code.from_asset(f"{__dirname}/layer.zip")
)
compatible_runtimes =

# or, a specific version or appid of aws-lambda-layer-kubectl:
layer = eks.KubectlLayer(self, "KubectlLayer",
    version="2.0.0", # optional
    application_id="..."
)
```

Pass it to `kubectlLayer` when you create or import a cluster:

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
cluster = eks.Cluster(self, "MyCluster",
    kubectl_layer=layer
)

# or
cluster = eks.Cluster.from_cluster_attributes(self, "MyCluster",
    kubectl_layer=layer
)
```

> Instructions on how to build `layer.zip` can be found
> [here](https://github.com/aws-samples/aws-lambda-layer-kubectl/blob/master/cdk/README.md).

#### Memory

By default, the kubectl provider is configured with 1024MiB of memory. You can use the `kubectlMemory` option to specify the memory size for the AWS Lambda function:

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
from aws_cdk.core import Size


eks.Cluster(self, "MyCluster",
    kubectl_memory=Size.gibibytes(4)
)

# or
eks.Cluster.from_cluster_attributes(self, "MyCluster",
    kubectl_memory=Size.gibibytes(4)
)
```

### ARM64 Support

Instance types with `ARM64` architecture are supported in both managed nodegroup and self-managed capacity. Simply specify an ARM64 `instanceType` (such as `m6g.medium`), and the latest
Amazon Linux 2 AMI for ARM64 will be automatically selected.

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
# add a managed ARM64 nodegroup
cluster.add_nodegroup_capacity("extra-ng-arm",
    instance_type=ec2.InstanceType("m6g.medium"),
    min_size=2
)

# add a self-managed ARM64 nodegroup
cluster.add_auto_scaling_group_capacity("self-ng-arm",
    instance_type=ec2.InstanceType("m6g.medium"),
    min_capacity=2
)
```

### Masters Role

When you create a cluster, you can specify a `mastersRole`. The `Cluster` construct will associate this role with the `system:masters` [RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/) group, giving it super-user access to the cluster.

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
role = iam.Role(...)
eks.Cluster(self, "HelloEKS",
    version=eks.KubernetesVersion.V1_18,
    masters_role=role
)
```

If you do not specify it, a default role will be created on your behalf, that can be assumed by anyone in the account with `sts:AssumeRole` permissions for this role.

This is the role you see as part of the stack outputs mentioned in the [Quick Start](#quick-start).

```console
$ aws eks update-kubeconfig --name cluster-xxxxx --role-arn arn:aws:iam::112233445566:role/yyyyy
Added new context arn:aws:eks:rrrrr:112233445566:cluster/cluster-xxxxx to /home/boom/.kube/config
```

The default value is `eks.EndpointAccess.PUBLIC_AND_PRIVATE`. Which means the cluster endpoint is accessible from outside of your VPC, but worker node traffic and `kubectl` commands issued by this library stay within your VPC.

### Encryption

When you create an Amazon EKS cluster, envelope encryption of Kubernetes secrets using the AWS Key Management Service (AWS KMS) can be enabled.
The documentation on [creating a cluster](https://docs.aws.amazon.com/eks/latest/userguide/create-cluster.html)
can provide more details about the customer master key (CMK) that can be used for the encryption.

You can use the `secretsEncryptionKey` to configure which key the cluster will use to encrypt Kubernetes secrets. By default, an AWS Managed key will be used.

> This setting can only be specified when the cluster is created and cannot be updated.

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
secrets_key = kms.Key(self, "SecretsKey")
cluster = eks.Cluster(self, "MyCluster",
    secrets_encryption_key=secrets_key
)
```

The Amazon Resource Name (ARN) for that CMK can be retrieved.

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
cluster_encryption_config_key_arn = cluster.cluster_encryption_config_key_arn
```

## Permissions and Security

Amazon EKS provides several mechanism of securing the cluster and granting permissions to specific IAM users and roles.

### AWS IAM Mapping

As described in the [Amazon EKS User Guide](https://docs.aws.amazon.com/en_us/eks/latest/userguide/add-user-role.html), you can map AWS IAM users and roles to [Kubernetes Role-based access control (RBAC)](https://kubernetes.io/docs/reference/access-authn-authz/rbac).

The Amazon EKS construct manages the *aws-auth* `ConfigMap` Kubernetes resource on your behalf and exposes an API through the `cluster.awsAuth` for mapping
users, roles and accounts.

Furthermore, when auto-scaling group capacity is added to the cluster, the IAM instance role of the auto-scaling group will be automatically mapped to RBAC so nodes can connect to the cluster. No manual mapping is required.

For example, let's say you want to grant an IAM user administrative privileges on your cluster:

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
admin_user = iam.User(self, "Admin")
cluster.aws_auth.add_user_mapping(admin_user, groups=["system:masters"])
```

A convenience method for mapping a role to the `system:masters` group is also available:

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
cluster.aws_auth.add_masters_role(role)
```

### Cluster Security Group

When you create an Amazon EKS cluster, a [cluster security group](https://docs.aws.amazon.com/eks/latest/userguide/sec-group-reqs.html)
is automatically created as well. This security group is designed to allow all traffic from the control plane and managed node groups to flow freely
between each other.

The ID for that security group can be retrieved after creating the cluster.

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
cluster_security_group_id = cluster.cluster_security_group_id
```

### Node SSH Access

If you want to be able to SSH into your worker nodes, you must already have an SSH key in the region you're connecting to and pass it when
you add capacity to the cluster. You must also be able to connect to the hosts (meaning they must have a public IP and you
should be allowed to connect to them on port 22):

See [SSH into nodes](test/example.ssh-into-nodes.lit.ts) for a code example.

If you want to SSH into nodes in a private subnet, you should set up a bastion host in a public subnet. That setup is recommended, but is
unfortunately beyond the scope of this documentation.

### Service Accounts

With services account you can provide Kubernetes Pods access to AWS resources.

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
# add service account
sa = cluster.add_service_account("MyServiceAccount")

bucket = Bucket(self, "Bucket")
bucket.grant_read_write(service_account)

mypod = cluster.add_manifest("mypod",
    api_version="v1",
    kind="Pod",
    metadata={"name": "mypod"},
    spec={
        "service_account_name": sa.service_account_name,
        "containers": [{
            "name": "hello",
            "image": "paulbouwer/hello-kubernetes:1.5",
            "ports": [{"container_port": 8080}]
        }
        ]
    }
)

# create the resource after the service account.
mypod.node.add_dependency(sa)

# print the IAM role arn for this service account
cdk.CfnOutput(self, "ServiceAccountIamRole", value=sa.role.role_arn)
```

Note that using `sa.serviceAccountName` above **does not** translate into a resource dependency.
This is why an explicit dependency is needed. See [https://github.com/aws/aws-cdk/issues/9910](https://github.com/aws/aws-cdk/issues/9910) for more details.

You can also add service accounts to existing clusters.
To do so, pass the `openIdConnectProvider` property when you import the cluster into the application.

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
# you can import an existing provider
provider = eks.OpenIdConnectProvider.from_open_id_connect_provider_arn(self, "Provider", "arn:aws:iam::123456:oidc-provider/oidc.eks.eu-west-1.amazonaws.com/id/AB123456ABC")

# or create a new one using an existing issuer url
provider = eks.OpenIdConnectProvider(self, "Provider", issuer_url)

cluster = eks.Cluster.from_cluster_attributes({
    "cluster_name": "Cluster",
    "open_id_connect_provider": provider,
    "kubectl_role_arn": "arn:aws:iam::123456:role/service-role/k8sservicerole"
})

sa = cluster.add_service_account("MyServiceAccount")

bucket = Bucket(self, "Bucket")
bucket.grant_read_write(service_account)
```

Note that adding service accounts requires running `kubectl` commands against the cluster.
This means you must also pass the `kubectlRoleArn` when importing the cluster.
See [Using existing Clusters](https://github.com/aws/aws-cdk/tree/master/packages/@aws-cdk/aws-eks#using-existing-clusters).

## Applying Kubernetes Resources

The library supports several popular resource deployment mechanisms, among which are:

### Kubernetes Manifests

The `KubernetesManifest` construct or `cluster.addManifest` method can be used
to apply Kubernetes resource manifests to this cluster.

> When using `cluster.addManifest`, the manifest construct is defined within the cluster's stack scope. If the manifest contains
> attributes from a different stack which depend on the cluster stack, a circular dependency will be created and you will get a synth time error.
> To avoid this, directly use `new KubernetesManifest` to create the manifest in the scope of the other stack.

The following examples will deploy the [paulbouwer/hello-kubernetes](https://github.com/paulbouwer/hello-kubernetes)
service on the cluster:

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
app_label = {"app": "hello-kubernetes"}

deployment = {
    "api_version": "apps/v1",
    "kind": "Deployment",
    "metadata": {"name": "hello-kubernetes"},
    "spec": {
        "replicas": 3,
        "selector": {"match_labels": app_label},
        "template": {
            "metadata": {"labels": app_label},
            "spec": {
                "containers": [{
                    "name": "hello-kubernetes",
                    "image": "paulbouwer/hello-kubernetes:1.5",
                    "ports": [{"container_port": 8080}]
                }
                ]
            }
        }
    }
}

service = {
    "api_version": "v1",
    "kind": "Service",
    "metadata": {"name": "hello-kubernetes"},
    "spec": {
        "type": "LoadBalancer",
        "ports": [{"port": 80, "target_port": 8080}],
        "selector": app_label
    }
}

# option 1: use a construct
KubernetesManifest(self, "hello-kub",
    cluster=cluster,
    manifest=[deployment, service]
)

# or, option2: use `addManifest`
cluster.add_manifest("hello-kub", service, deployment)
```

#### Adding resources from a URL

The following example will deploy the resource manifest hosting on remote server:

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
import js_yaml as yaml
import sync_request as request


manifest_url = "https://url/of/manifest.yaml"
manifest = yaml.safe_load_all(request("GET", manifest_url).get_body())
cluster.add_manifest("my-resource", (SpreadElement ...manifest
  manifest))
```

#### Dependencies

There are cases where Kubernetes resources must be deployed in a specific order.
For example, you cannot define a resource in a Kubernetes namespace before the
namespace was created.

You can represent dependencies between `KubernetesManifest`s using
`resource.node.addDependency()`:

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
namespace = cluster.add_manifest("my-namespace",
    api_version="v1",
    kind="Namespace",
    metadata={"name": "my-app"}
)

service = cluster.add_manifest("my-service",
    metadata={
        "name": "myservice",
        "namespace": "my-app"
    },
    spec=
)

service.node.add_dependency(namespace)
```

**NOTE:** when a `KubernetesManifest` includes multiple resources (either directly
or through `cluster.addManifest()`) (e.g. `cluster.addManifest('foo', r1, r2, r3,...)`), these resources will be applied as a single manifest via `kubectl`
and will be applied sequentially (the standard behavior in `kubectl`).

---


Since Kubernetes manifests are implemented as CloudFormation resources in the
CDK. This means that if the manifest is deleted from your code (or the stack is
deleted), the next `cdk deploy` will issue a `kubectl delete` command and the
Kubernetes resources in that manifest will be deleted.

#### Resource Pruning

When a resource is deleted from a Kubernetes manifest, the EKS module will
automatically delete these resources by injecting a *prune label* to all
manifest resources. This label is then passed to [`kubectl apply --prune`](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/declarative-config/#alternative-kubectl-apply-f-directory-prune-l-your-label).

Pruning is enabled by default but can be disabled through the `prune` option
when a cluster is defined:

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
Cluster(self, "MyCluster",
    prune=False
)
```

### Helm Charts

The `HelmChart` construct or `cluster.addHelmChart` method can be used
to add Kubernetes resources to this cluster using Helm.

> When using `cluster.addHelmChart`, the manifest construct is defined within the cluster's stack scope. If the manifest contains
> attributes from a different stack which depend on the cluster stack, a circular dependency will be created and you will get a synth time error.
> To avoid this, directly use `new HelmChart` to create the chart in the scope of the other stack.

The following example will install the [NGINX Ingress Controller](https://kubernetes.github.io/ingress-nginx/) to your cluster using Helm.

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
# option 1: use a construct
HelmChart(self, "NginxIngress",
    cluster=cluster,
    chart="nginx-ingress",
    repository="https://helm.nginx.com/stable",
    namespace="kube-system"
)

# or, option2: use `addHelmChart`
cluster.add_helm_chart("NginxIngress",
    chart="nginx-ingress",
    repository="https://helm.nginx.com/stable",
    namespace="kube-system"
)
```

Helm charts will be installed and updated using `helm upgrade --install`, where a few parameters
are being passed down (such as `repo`, `values`, `version`, `namespace`, `wait`, `timeout`, etc).
This means that if the chart is added to CDK with the same release name, it will try to update
the chart in the cluster.

Helm charts are implemented as CloudFormation resources in CDK.
This means that if the chart is deleted from your code (or the stack is
deleted), the next `cdk deploy` will issue a `helm uninstall` command and the
Helm chart will be deleted.

When there is no `release` defined, a unique ID will be allocated for the release based
on the construct path.

By default, all Helm charts will be installed concurrently. In some cases, this
could cause race conditions where two Helm charts attempt to deploy the same
resource or if Helm charts depend on each other. You can use
`chart.node.addDependency()` in order to declare a dependency order between
charts:

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
chart1 = cluster.add_helm_chart(...)
chart2 = cluster.add_helm_chart(...)

chart2.node.add_dependency(chart1)
```

#### CDK8s Charts

[CDK8s](https://cdk8s.io/) is an open-source library that enables Kubernetes manifest authoring using familiar programming languages. It is founded on the same technologies as the AWS CDK, such as [`constructs`](https://github.com/aws/constructs) and [`jsii`](https://github.com/aws/jsii).

> To learn more about cdk8s, visit the [Getting Started](https://github.com/awslabs/cdk8s/tree/master/docs/getting-started) tutorials.

The EKS module natively integrates with cdk8s and allows you to apply cdk8s charts on AWS EKS clusters via the `cluster.addCdk8sChart` method.

In addition to `cdk8s`, you can also use [`cdk8s+`](https://github.com/awslabs/cdk8s/tree/master/packages/cdk8s-plus), which provides higher level abstraction for the core kubernetes api objects.
You can think of it like the `L2` constructs for Kubernetes. Any other `cdk8s` based libraries are also supported, for example [`cdk8s-debore`](https://github.com/toricls/cdk8s-debore).

To get started, add the following dependencies to your `package.json` file:

```json
"dependencies": {
  "cdk8s": "0.30.0",
  "cdk8s-plus": "0.30.0",
  "constructs": "3.0.4"
}
```

> Note that the version of `cdk8s` must be `>=0.30.0`.

Similarly to how you would create a stack by extending `@aws-cdk/core.Stack`, we recommend you create a chart of your own that extends `cdk8s.Chart`,
and add your kubernetes resources to it. You can use `aws-cdk` construct attributes and properties inside your `cdk8s` construct freely.

In this example we create a chart that accepts an `s3.Bucket` and passes its name to a kubernetes pod as an environment variable.

Notice that the chart must accept a `constructs.Construct` type as its scope, not an `@aws-cdk/core.Construct` as you would normally use.
For this reason, to avoid possible confusion, we will create the chart in a separate file:

`+ my-chart.ts`

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
import aws_cdk.aws_s3 as s3
import constructs as constructs
import cdk8s as cdk8s
import cdk8s_plus as kplus


class MyChart(cdk8s.Chart):
    def __init__(self, scope, id, *, bucket):
        super().__init__(scope, id)

        kplus.Pod(self, "Pod",
            spec={
                "containers": [
                    kplus.Container(
                        image="my-image",
                        env={
                            "BUCKET_NAME": kplus.EnvValue.from_value(bucket.bucket_name)
                        }
                    )
                ]
            }
        )
```

Then, in your AWS CDK app:

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
import aws_cdk.aws_s3 as s3
import cdk8s as cdk8s
from ..my_chart import MyChart


# some bucket..
bucket = s3.Bucket(self, "Bucket")

# create a cdk8s chart and use `cdk8s.App` as the scope.
my_chart = MyChart(cdk8s.App(), "MyChart", bucket=bucket)

# add the cdk8s chart to the cluster
cluster.add_cdk8s_chart("my-chart", my_chart)
```

##### Custom CDK8s Constructs

You can also compose a few stock `cdk8s+` constructs into your own custom construct. However, since mixing scopes between `aws-cdk` and `cdk8s` is currently not supported, the `Construct` class
you'll need to use is the one from the [`constructs`](https://github.com/aws/constructs) module, and not from `@aws-cdk/core` like you normally would.
This is why we used `new cdk8s.App()` as the scope of the chart above.

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
import constructs as constructs
import cdk8s as cdk8s
import cdk8s_plus as kplus


class LoadBalancedWebService(constructs.Construct):
    def __init__(self, scope, id, props):
        super().__init__(scope, id)

        deployment = kplus.Deployment(chart, "Deployment",
            spec={
                "replicas": props.replicas,
                "pod_spec_template": {
                    "containers": [kplus.Container(image=props.image)]
                }
            }
        )

        deployment.expose(port=props.port, service_type=kplus.ServiceType.LOAD_BALANCER)
```

##### Manually importing k8s specs and CRD's

If you find yourself unable to use `cdk8s+`, or just like to directly use the `k8s` native objects or CRD's, you can do so by manually importing them using the `cdk8s-cli`.

See [Importing kubernetes objects](https://github.com/awslabs/cdk8s/tree/master/packages/cdk8s-cli#import) for detailed instructions.

## Patching Kubernetes Resources

The `KubernetesPatch` construct can be used to update existing kubernetes
resources. The following example can be used to patch the `hello-kubernetes`
deployment from the example above with 5 replicas.

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
KubernetesPatch(self, "hello-kub-deployment-label",
    cluster=cluster,
    resource_name="deployment/hello-kubernetes",
    apply_patch={"spec": {"replicas": 5}},
    restore_patch={"spec": {"replicas": 3}}
)
```

## Querying Kubernetes Resources

The `KubernetesObjectValue` construct can be used to query for information about kubernetes objects,
and use that as part of your CDK application.

For example, you can fetch the address of a [`LoadBalancer`](https://kubernetes.io/docs/concepts/services-networking/service/#loadbalancer) type service:

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
# query the load balancer address
my_service_address = KubernetesObjectValue(self, "LoadBalancerAttribute",
    cluster=cluster,
    object_type="service",
    object_name="my-service",
    json_path=".status.loadBalancer.ingress[0].hostname"
)

# pass the address to a lambda function
proxy_function = lambda_.Function(self, "ProxyFunction", {
    (SpreadAssignment ...
      environment
      environment)
},
    my_service_address=my_service_address.value
)
```

Specifically, since the above use-case is quite common, there is an easier way to access that information:

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
load_balancer_address = cluster.get_service_load_balancer_address("my-service")
```

## Using existing clusters

The Amazon EKS library allows defining Kubernetes resources such as [Kubernetes
manifests](#kubernetes-resources) and [Helm charts](#helm-charts) on clusters
that are not defined as part of your CDK app.

First, you'll need to "import" a cluster to your CDK app. To do that, use the
`eks.Cluster.fromClusterAttributes()` static method:

```python
# Example automatically generated. See https://github.com/aws/jsii/issues/826
cluster = eks.Cluster.from_cluster_attributes(self, "MyCluster",
    cluster_name="my-cluster-name",
    kubectl_role_arn="arn:aws:iam::1111111:role/iam-role-that-has-masters-access"
)
```

Then, you can use `addManifest` or `addHelmChart` to define resources inside
your Kubernetes cluster. For example:

```python
# Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
cluster.add_manifest("Test",
    api_version="v1",
    kind="ConfigMap",
    metadata={
        "name": "myconfigmap"
    },
    data={
        "Key": "value",
        "Another": "123454"
    }
)
```

At the minimum, when importing clusters for `kubectl` management, you will need
to specify:

* `clusterName` - the name of the cluster.
* `kubectlRoleArn` - the ARN of an IAM role mapped to the `system:masters` RBAC
  role. If the cluster you are importing was created using the AWS CDK, the
  CloudFormation stack has an output that includes an IAM role that can be used.
  Otherwise, you can create an IAM role and map it to `system:masters` manually.
  The trust policy of this role should include the the
  `arn:aws::iam::${accountId}:root` principal in order to allow the execution
  role of the kubectl resource to assume it.

If the cluster is configured with private-only or private and restricted public
Kubernetes [endpoint access](#endpoint-access), you must also specify:

* `kubectlSecurityGroupId` - the ID of an EC2 security group that is allowed
  connections to the cluster's control security group. For example, the EKS managed [cluster security group](#cluster-security-group).
* `kubectlPrivateSubnetIds` - a list of private VPC subnets IDs that will be used
  to access the Kubernetes endpoint.

## Known Issues and Limitations

* [One cluster per stack](https://github.com/aws/aws-cdk/issues/10073)
* [Service Account dependencies](https://github.com/aws/aws-cdk/issues/9910)
* [Support isolated VPCs](https://github.com/aws/aws-cdk/issues/12171)
"""
import abc
import builtins
import datetime
import enum
import typing

import jsii
import publication
import typing_extensions

from ._jsii import *

import aws_cdk.aws_autoscaling
import aws_cdk.aws_ec2
import aws_cdk.aws_iam
import aws_cdk.aws_kms
import aws_cdk.aws_lambda
import aws_cdk.aws_sns
import aws_cdk.core
import constructs


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.AutoScalingGroupCapacityOptions",
    jsii_struct_bases=[aws_cdk.aws_autoscaling.CommonAutoScalingGroupProps],
    name_mapping={
        "allow_all_outbound": "allowAllOutbound",
        "associate_public_ip_address": "associatePublicIpAddress",
        "auto_scaling_group_name": "autoScalingGroupName",
        "block_devices": "blockDevices",
        "cooldown": "cooldown",
        "desired_capacity": "desiredCapacity",
        "group_metrics": "groupMetrics",
        "health_check": "healthCheck",
        "ignore_unmodified_size_properties": "ignoreUnmodifiedSizeProperties",
        "instance_monitoring": "instanceMonitoring",
        "key_name": "keyName",
        "max_capacity": "maxCapacity",
        "max_instance_lifetime": "maxInstanceLifetime",
        "min_capacity": "minCapacity",
        "notifications": "notifications",
        "notifications_topic": "notificationsTopic",
        "replacing_update_min_successful_instances_percent": "replacingUpdateMinSuccessfulInstancesPercent",
        "resource_signal_count": "resourceSignalCount",
        "resource_signal_timeout": "resourceSignalTimeout",
        "rolling_update_configuration": "rollingUpdateConfiguration",
        "signals": "signals",
        "spot_price": "spotPrice",
        "update_policy": "updatePolicy",
        "update_type": "updateType",
        "vpc_subnets": "vpcSubnets",
        "instance_type": "instanceType",
        "bootstrap_enabled": "bootstrapEnabled",
        "bootstrap_options": "bootstrapOptions",
        "machine_image_type": "machineImageType",
        "map_role": "mapRole",
    },
)
class AutoScalingGroupCapacityOptions(
    aws_cdk.aws_autoscaling.CommonAutoScalingGroupProps,
):
    def __init__(
        self,
        *,
        allow_all_outbound: typing.Optional[builtins.bool] = None,
        associate_public_ip_address: typing.Optional[builtins.bool] = None,
        auto_scaling_group_name: typing.Optional[builtins.str] = None,
        block_devices: typing.Optional[typing.List[aws_cdk.aws_autoscaling.BlockDevice]] = None,
        cooldown: typing.Optional[aws_cdk.core.Duration] = None,
        desired_capacity: typing.Optional[jsii.Number] = None,
        group_metrics: typing.Optional[typing.List[aws_cdk.aws_autoscaling.GroupMetrics]] = None,
        health_check: typing.Optional[aws_cdk.aws_autoscaling.HealthCheck] = None,
        ignore_unmodified_size_properties: typing.Optional[builtins.bool] = None,
        instance_monitoring: typing.Optional[aws_cdk.aws_autoscaling.Monitoring] = None,
        key_name: typing.Optional[builtins.str] = None,
        max_capacity: typing.Optional[jsii.Number] = None,
        max_instance_lifetime: typing.Optional[aws_cdk.core.Duration] = None,
        min_capacity: typing.Optional[jsii.Number] = None,
        notifications: typing.Optional[typing.List[aws_cdk.aws_autoscaling.NotificationConfiguration]] = None,
        notifications_topic: typing.Optional[aws_cdk.aws_sns.ITopic] = None,
        replacing_update_min_successful_instances_percent: typing.Optional[jsii.Number] = None,
        resource_signal_count: typing.Optional[jsii.Number] = None,
        resource_signal_timeout: typing.Optional[aws_cdk.core.Duration] = None,
        rolling_update_configuration: typing.Optional[aws_cdk.aws_autoscaling.RollingUpdateConfiguration] = None,
        signals: typing.Optional[aws_cdk.aws_autoscaling.Signals] = None,
        spot_price: typing.Optional[builtins.str] = None,
        update_policy: typing.Optional[aws_cdk.aws_autoscaling.UpdatePolicy] = None,
        update_type: typing.Optional[aws_cdk.aws_autoscaling.UpdateType] = None,
        vpc_subnets: typing.Optional[aws_cdk.aws_ec2.SubnetSelection] = None,
        instance_type: aws_cdk.aws_ec2.InstanceType,
        bootstrap_enabled: typing.Optional[builtins.bool] = None,
        bootstrap_options: typing.Optional["BootstrapOptions"] = None,
        machine_image_type: typing.Optional["MachineImageType"] = None,
        map_role: typing.Optional[builtins.bool] = None,
    ) -> None:
        """(experimental) Options for adding worker nodes.

        :param allow_all_outbound: Whether the instances can initiate connections to anywhere by default. Default: true
        :param associate_public_ip_address: Whether instances in the Auto Scaling Group should have public IP addresses associated with them. Default: - Use subnet setting.
        :param auto_scaling_group_name: The name of the Auto Scaling group. This name must be unique per Region per account. Default: - Auto generated by CloudFormation
        :param block_devices: Specifies how block devices are exposed to the instance. You can specify virtual devices and EBS volumes. Each instance that is launched has an associated root device volume, either an Amazon EBS volume or an instance store volume. You can use block device mappings to specify additional EBS volumes or instance store volumes to attach to an instance when it is launched. Default: - Uses the block device mapping of the AMI
        :param cooldown: Default scaling cooldown for this AutoScalingGroup. Default: Duration.minutes(5)
        :param desired_capacity: Initial amount of instances in the fleet. If this is set to a number, every deployment will reset the amount of instances to this number. It is recommended to leave this value blank. Default: minCapacity, and leave unchanged during deployment
        :param group_metrics: Enable monitoring for group metrics, these metrics describe the group rather than any of its instances. To report all group metrics use ``GroupMetrics.all()`` Group metrics are reported in a granularity of 1 minute at no additional charge. Default: - no group metrics will be reported
        :param health_check: Configuration for health checks. Default: - HealthCheck.ec2 with no grace period
        :param ignore_unmodified_size_properties: If the ASG has scheduled actions, don't reset unchanged group sizes. Only used if the ASG has scheduled actions (which may scale your ASG up or down regardless of cdk deployments). If true, the size of the group will only be reset if it has been changed in the CDK app. If false, the sizes will always be changed back to what they were in the CDK app on deployment. Default: true
        :param instance_monitoring: Controls whether instances in this group are launched with detailed or basic monitoring. When detailed monitoring is enabled, Amazon CloudWatch generates metrics every minute and your account is charged a fee. When you disable detailed monitoring, CloudWatch generates metrics every 5 minutes. Default: - Monitoring.DETAILED
        :param key_name: Name of SSH keypair to grant access to instances. Default: - No SSH access will be possible.
        :param max_capacity: Maximum number of instances in the fleet. Default: desiredCapacity
        :param max_instance_lifetime: The maximum amount of time that an instance can be in service. The maximum duration applies to all current and future instances in the group. As an instance approaches its maximum duration, it is terminated and replaced, and cannot be used again. You must specify a value of at least 604,800 seconds (7 days). To clear a previously set value, leave this property undefined. Default: none
        :param min_capacity: Minimum number of instances in the fleet. Default: 1
        :param notifications: Configure autoscaling group to send notifications about fleet changes to an SNS topic(s). Default: - No fleet change notifications will be sent.
        :param notifications_topic: (deprecated) SNS topic to send notifications about fleet changes. Default: - No fleet change notifications will be sent.
        :param replacing_update_min_successful_instances_percent: (deprecated) Configuration for replacing updates. Only used if updateType == UpdateType.ReplacingUpdate. Specifies how many instances must signal success for the update to succeed. Default: minSuccessfulInstancesPercent
        :param resource_signal_count: (deprecated) How many ResourceSignal calls CloudFormation expects before the resource is considered created. Default: 1 if resourceSignalTimeout is set, 0 otherwise
        :param resource_signal_timeout: (deprecated) The length of time to wait for the resourceSignalCount. The maximum value is 43200 (12 hours). Default: Duration.minutes(5) if resourceSignalCount is set, N/A otherwise
        :param rolling_update_configuration: (deprecated) Configuration for rolling updates. Only used if updateType == UpdateType.RollingUpdate. Default: - RollingUpdateConfiguration with defaults.
        :param signals: Configure waiting for signals during deployment. Use this to pause the CloudFormation deployment to wait for the instances in the AutoScalingGroup to report successful startup during creation and updates. The UserData script needs to invoke ``cfn-signal`` with a success or failure code after it is done setting up the instance. Without waiting for signals, the CloudFormation deployment will proceed as soon as the AutoScalingGroup has been created or updated but before the instances in the group have been started. For example, to have instances wait for an Elastic Load Balancing health check before they signal success, add a health-check verification by using the cfn-init helper script. For an example, see the verify_instance_health command in the Auto Scaling rolling updates sample template: https://github.com/awslabs/aws-cloudformation-templates/blob/master/aws/services/AutoScaling/AutoScalingRollingUpdates.yaml Default: - Do not wait for signals
        :param spot_price: The maximum hourly price (in USD) to be paid for any Spot Instance launched to fulfill the request. Spot Instances are launched when the price you specify exceeds the current Spot market price. Default: none
        :param update_policy: What to do when an AutoScalingGroup's instance configuration is changed. This is applied when any of the settings on the ASG are changed that affect how the instances should be created (VPC, instance type, startup scripts, etc.). It indicates how the existing instances should be replaced with new instances matching the new config. By default, nothing is done and only new instances are launched with the new config. Default: - ``UpdatePolicy.rollingUpdate()`` if using ``init``, ``UpdatePolicy.none()`` otherwise
        :param update_type: (deprecated) What to do when an AutoScalingGroup's instance configuration is changed. This is applied when any of the settings on the ASG are changed that affect how the instances should be created (VPC, instance type, startup scripts, etc.). It indicates how the existing instances should be replaced with new instances matching the new config. By default, nothing is done and only new instances are launched with the new config. Default: UpdateType.None
        :param vpc_subnets: Where to place instances within the VPC. Default: - All Private subnets.
        :param instance_type: (experimental) Instance type of the instances to start.
        :param bootstrap_enabled: (experimental) Configures the EC2 user-data script for instances in this autoscaling group to bootstrap the node (invoke ``/etc/eks/bootstrap.sh``) and associate it with the EKS cluster. If you wish to provide a custom user data script, set this to ``false`` and manually invoke ``autoscalingGroup.addUserData()``. Default: true
        :param bootstrap_options: (experimental) EKS node bootstrapping options. Default: - none
        :param machine_image_type: (experimental) Machine image type. Default: MachineImageType.AMAZON_LINUX_2
        :param map_role: (experimental) Will automatically update the aws-auth ConfigMap to map the IAM instance role to RBAC. This cannot be explicitly set to ``true`` if the cluster has kubectl disabled. Default: - true if the cluster has kubectl enabled (which is the default).

        :stability: experimental
        """
        if isinstance(rolling_update_configuration, dict):
            rolling_update_configuration = aws_cdk.aws_autoscaling.RollingUpdateConfiguration(**rolling_update_configuration)
        if isinstance(vpc_subnets, dict):
            vpc_subnets = aws_cdk.aws_ec2.SubnetSelection(**vpc_subnets)
        if isinstance(bootstrap_options, dict):
            bootstrap_options = BootstrapOptions(**bootstrap_options)
        self._values: typing.Dict[str, typing.Any] = {
            "instance_type": instance_type,
        }
        if allow_all_outbound is not None:
            self._values["allow_all_outbound"] = allow_all_outbound
        if associate_public_ip_address is not None:
            self._values["associate_public_ip_address"] = associate_public_ip_address
        if auto_scaling_group_name is not None:
            self._values["auto_scaling_group_name"] = auto_scaling_group_name
        if block_devices is not None:
            self._values["block_devices"] = block_devices
        if cooldown is not None:
            self._values["cooldown"] = cooldown
        if desired_capacity is not None:
            self._values["desired_capacity"] = desired_capacity
        if group_metrics is not None:
            self._values["group_metrics"] = group_metrics
        if health_check is not None:
            self._values["health_check"] = health_check
        if ignore_unmodified_size_properties is not None:
            self._values["ignore_unmodified_size_properties"] = ignore_unmodified_size_properties
        if instance_monitoring is not None:
            self._values["instance_monitoring"] = instance_monitoring
        if key_name is not None:
            self._values["key_name"] = key_name
        if max_capacity is not None:
            self._values["max_capacity"] = max_capacity
        if max_instance_lifetime is not None:
            self._values["max_instance_lifetime"] = max_instance_lifetime
        if min_capacity is not None:
            self._values["min_capacity"] = min_capacity
        if notifications is not None:
            self._values["notifications"] = notifications
        if notifications_topic is not None:
            self._values["notifications_topic"] = notifications_topic
        if replacing_update_min_successful_instances_percent is not None:
            self._values["replacing_update_min_successful_instances_percent"] = replacing_update_min_successful_instances_percent
        if resource_signal_count is not None:
            self._values["resource_signal_count"] = resource_signal_count
        if resource_signal_timeout is not None:
            self._values["resource_signal_timeout"] = resource_signal_timeout
        if rolling_update_configuration is not None:
            self._values["rolling_update_configuration"] = rolling_update_configuration
        if signals is not None:
            self._values["signals"] = signals
        if spot_price is not None:
            self._values["spot_price"] = spot_price
        if update_policy is not None:
            self._values["update_policy"] = update_policy
        if update_type is not None:
            self._values["update_type"] = update_type
        if vpc_subnets is not None:
            self._values["vpc_subnets"] = vpc_subnets
        if bootstrap_enabled is not None:
            self._values["bootstrap_enabled"] = bootstrap_enabled
        if bootstrap_options is not None:
            self._values["bootstrap_options"] = bootstrap_options
        if machine_image_type is not None:
            self._values["machine_image_type"] = machine_image_type
        if map_role is not None:
            self._values["map_role"] = map_role

    @builtins.property
    def allow_all_outbound(self) -> typing.Optional[builtins.bool]:
        """Whether the instances can initiate connections to anywhere by default.

        :default: true
        """
        result = self._values.get("allow_all_outbound")
        return result

    @builtins.property
    def associate_public_ip_address(self) -> typing.Optional[builtins.bool]:
        """Whether instances in the Auto Scaling Group should have public IP addresses associated with them.

        :default: - Use subnet setting.
        """
        result = self._values.get("associate_public_ip_address")
        return result

    @builtins.property
    def auto_scaling_group_name(self) -> typing.Optional[builtins.str]:
        """The name of the Auto Scaling group.

        This name must be unique per Region per account.

        :default: - Auto generated by CloudFormation
        """
        result = self._values.get("auto_scaling_group_name")
        return result

    @builtins.property
    def block_devices(
        self,
    ) -> typing.Optional[typing.List[aws_cdk.aws_autoscaling.BlockDevice]]:
        """Specifies how block devices are exposed to the instance. You can specify virtual devices and EBS volumes.

        Each instance that is launched has an associated root device volume,
        either an Amazon EBS volume or an instance store volume.
        You can use block device mappings to specify additional EBS volumes or
        instance store volumes to attach to an instance when it is launched.

        :default: - Uses the block device mapping of the AMI

        :see: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/block-device-mapping-concepts.html
        """
        result = self._values.get("block_devices")
        return result

    @builtins.property
    def cooldown(self) -> typing.Optional[aws_cdk.core.Duration]:
        """Default scaling cooldown for this AutoScalingGroup.

        :default: Duration.minutes(5)
        """
        result = self._values.get("cooldown")
        return result

    @builtins.property
    def desired_capacity(self) -> typing.Optional[jsii.Number]:
        """Initial amount of instances in the fleet.

        If this is set to a number, every deployment will reset the amount of
        instances to this number. It is recommended to leave this value blank.

        :default: minCapacity, and leave unchanged during deployment

        :see: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-as-group.html#cfn-as-group-desiredcapacity
        """
        result = self._values.get("desired_capacity")
        return result

    @builtins.property
    def group_metrics(
        self,
    ) -> typing.Optional[typing.List[aws_cdk.aws_autoscaling.GroupMetrics]]:
        """Enable monitoring for group metrics, these metrics describe the group rather than any of its instances.

        To report all group metrics use ``GroupMetrics.all()``
        Group metrics are reported in a granularity of 1 minute at no additional charge.

        :default: - no group metrics will be reported
        """
        result = self._values.get("group_metrics")
        return result

    @builtins.property
    def health_check(self) -> typing.Optional[aws_cdk.aws_autoscaling.HealthCheck]:
        """Configuration for health checks.

        :default: - HealthCheck.ec2 with no grace period
        """
        result = self._values.get("health_check")
        return result

    @builtins.property
    def ignore_unmodified_size_properties(self) -> typing.Optional[builtins.bool]:
        """If the ASG has scheduled actions, don't reset unchanged group sizes.

        Only used if the ASG has scheduled actions (which may scale your ASG up
        or down regardless of cdk deployments). If true, the size of the group
        will only be reset if it has been changed in the CDK app. If false, the
        sizes will always be changed back to what they were in the CDK app
        on deployment.

        :default: true
        """
        result = self._values.get("ignore_unmodified_size_properties")
        return result

    @builtins.property
    def instance_monitoring(
        self,
    ) -> typing.Optional[aws_cdk.aws_autoscaling.Monitoring]:
        """Controls whether instances in this group are launched with detailed or basic monitoring.

        When detailed monitoring is enabled, Amazon CloudWatch generates metrics every minute and your account
        is charged a fee. When you disable detailed monitoring, CloudWatch generates metrics every 5 minutes.

        :default: - Monitoring.DETAILED

        :see: https://docs.aws.amazon.com/autoscaling/latest/userguide/as-instance-monitoring.html#enable-as-instance-metrics
        """
        result = self._values.get("instance_monitoring")
        return result

    @builtins.property
    def key_name(self) -> typing.Optional[builtins.str]:
        """Name of SSH keypair to grant access to instances.

        :default: - No SSH access will be possible.
        """
        result = self._values.get("key_name")
        return result

    @builtins.property
    def max_capacity(self) -> typing.Optional[jsii.Number]:
        """Maximum number of instances in the fleet.

        :default: desiredCapacity
        """
        result = self._values.get("max_capacity")
        return result

    @builtins.property
    def max_instance_lifetime(self) -> typing.Optional[aws_cdk.core.Duration]:
        """The maximum amount of time that an instance can be in service.

        The maximum duration applies
        to all current and future instances in the group. As an instance approaches its maximum duration,
        it is terminated and replaced, and cannot be used again.

        You must specify a value of at least 604,800 seconds (7 days). To clear a previously set value,
        leave this property undefined.

        :default: none

        :see: https://docs.aws.amazon.com/autoscaling/ec2/userguide/asg-max-instance-lifetime.html
        """
        result = self._values.get("max_instance_lifetime")
        return result

    @builtins.property
    def min_capacity(self) -> typing.Optional[jsii.Number]:
        """Minimum number of instances in the fleet.

        :default: 1
        """
        result = self._values.get("min_capacity")
        return result

    @builtins.property
    def notifications(
        self,
    ) -> typing.Optional[typing.List[aws_cdk.aws_autoscaling.NotificationConfiguration]]:
        """Configure autoscaling group to send notifications about fleet changes to an SNS topic(s).

        :default: - No fleet change notifications will be sent.

        :see: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-as-group.html#cfn-as-group-notificationconfigurations
        """
        result = self._values.get("notifications")
        return result

    @builtins.property
    def notifications_topic(self) -> typing.Optional[aws_cdk.aws_sns.ITopic]:
        """(deprecated) SNS topic to send notifications about fleet changes.

        :default: - No fleet change notifications will be sent.

        :deprecated: use ``notifications``

        :stability: deprecated
        """
        result = self._values.get("notifications_topic")
        return result

    @builtins.property
    def replacing_update_min_successful_instances_percent(
        self,
    ) -> typing.Optional[jsii.Number]:
        """(deprecated) Configuration for replacing updates.

        Only used if updateType == UpdateType.ReplacingUpdate. Specifies how
        many instances must signal success for the update to succeed.

        :default: minSuccessfulInstancesPercent

        :deprecated: Use ``signals`` instead

        :stability: deprecated
        """
        result = self._values.get("replacing_update_min_successful_instances_percent")
        return result

    @builtins.property
    def resource_signal_count(self) -> typing.Optional[jsii.Number]:
        """(deprecated) How many ResourceSignal calls CloudFormation expects before the resource is considered created.

        :default: 1 if resourceSignalTimeout is set, 0 otherwise

        :deprecated: Use ``signals`` instead.

        :stability: deprecated
        """
        result = self._values.get("resource_signal_count")
        return result

    @builtins.property
    def resource_signal_timeout(self) -> typing.Optional[aws_cdk.core.Duration]:
        """(deprecated) The length of time to wait for the resourceSignalCount.

        The maximum value is 43200 (12 hours).

        :default: Duration.minutes(5) if resourceSignalCount is set, N/A otherwise

        :deprecated: Use ``signals`` instead.

        :stability: deprecated
        """
        result = self._values.get("resource_signal_timeout")
        return result

    @builtins.property
    def rolling_update_configuration(
        self,
    ) -> typing.Optional[aws_cdk.aws_autoscaling.RollingUpdateConfiguration]:
        """(deprecated) Configuration for rolling updates.

        Only used if updateType == UpdateType.RollingUpdate.

        :default: - RollingUpdateConfiguration with defaults.

        :deprecated: Use ``updatePolicy`` instead

        :stability: deprecated
        """
        result = self._values.get("rolling_update_configuration")
        return result

    @builtins.property
    def signals(self) -> typing.Optional[aws_cdk.aws_autoscaling.Signals]:
        """Configure waiting for signals during deployment.

        Use this to pause the CloudFormation deployment to wait for the instances
        in the AutoScalingGroup to report successful startup during
        creation and updates. The UserData script needs to invoke ``cfn-signal``
        with a success or failure code after it is done setting up the instance.

        Without waiting for signals, the CloudFormation deployment will proceed as
        soon as the AutoScalingGroup has been created or updated but before the
        instances in the group have been started.

        For example, to have instances wait for an Elastic Load Balancing health check before
        they signal success, add a health-check verification by using the
        cfn-init helper script. For an example, see the verify_instance_health
        command in the Auto Scaling rolling updates sample template:

        https://github.com/awslabs/aws-cloudformation-templates/blob/master/aws/services/AutoScaling/AutoScalingRollingUpdates.yaml

        :default: - Do not wait for signals
        """
        result = self._values.get("signals")
        return result

    @builtins.property
    def spot_price(self) -> typing.Optional[builtins.str]:
        """The maximum hourly price (in USD) to be paid for any Spot Instance launched to fulfill the request.

        Spot Instances are
        launched when the price you specify exceeds the current Spot market price.

        :default: none
        """
        result = self._values.get("spot_price")
        return result

    @builtins.property
    def update_policy(self) -> typing.Optional[aws_cdk.aws_autoscaling.UpdatePolicy]:
        """What to do when an AutoScalingGroup's instance configuration is changed.

        This is applied when any of the settings on the ASG are changed that
        affect how the instances should be created (VPC, instance type, startup
        scripts, etc.). It indicates how the existing instances should be
        replaced with new instances matching the new config. By default, nothing
        is done and only new instances are launched with the new config.

        :default: - ``UpdatePolicy.rollingUpdate()`` if using ``init``, ``UpdatePolicy.none()`` otherwise
        """
        result = self._values.get("update_policy")
        return result

    @builtins.property
    def update_type(self) -> typing.Optional[aws_cdk.aws_autoscaling.UpdateType]:
        """(deprecated) What to do when an AutoScalingGroup's instance configuration is changed.

        This is applied when any of the settings on the ASG are changed that
        affect how the instances should be created (VPC, instance type, startup
        scripts, etc.). It indicates how the existing instances should be
        replaced with new instances matching the new config. By default, nothing
        is done and only new instances are launched with the new config.

        :default: UpdateType.None

        :deprecated: Use ``updatePolicy`` instead

        :stability: deprecated
        """
        result = self._values.get("update_type")
        return result

    @builtins.property
    def vpc_subnets(self) -> typing.Optional[aws_cdk.aws_ec2.SubnetSelection]:
        """Where to place instances within the VPC.

        :default: - All Private subnets.
        """
        result = self._values.get("vpc_subnets")
        return result

    @builtins.property
    def instance_type(self) -> aws_cdk.aws_ec2.InstanceType:
        """(experimental) Instance type of the instances to start.

        :stability: experimental
        """
        result = self._values.get("instance_type")
        assert result is not None, "Required property 'instance_type' is missing"
        return result

    @builtins.property
    def bootstrap_enabled(self) -> typing.Optional[builtins.bool]:
        """(experimental) Configures the EC2 user-data script for instances in this autoscaling group to bootstrap the node (invoke ``/etc/eks/bootstrap.sh``) and associate it with the EKS cluster.

        If you wish to provide a custom user data script, set this to ``false`` and
        manually invoke ``autoscalingGroup.addUserData()``.

        :default: true

        :stability: experimental
        """
        result = self._values.get("bootstrap_enabled")
        return result

    @builtins.property
    def bootstrap_options(self) -> typing.Optional["BootstrapOptions"]:
        """(experimental) EKS node bootstrapping options.

        :default: - none

        :stability: experimental
        """
        result = self._values.get("bootstrap_options")
        return result

    @builtins.property
    def machine_image_type(self) -> typing.Optional["MachineImageType"]:
        """(experimental) Machine image type.

        :default: MachineImageType.AMAZON_LINUX_2

        :stability: experimental
        """
        result = self._values.get("machine_image_type")
        return result

    @builtins.property
    def map_role(self) -> typing.Optional[builtins.bool]:
        """(experimental) Will automatically update the aws-auth ConfigMap to map the IAM instance role to RBAC.

        This cannot be explicitly set to ``true`` if the cluster has kubectl disabled.

        :default: - true if the cluster has kubectl enabled (which is the default).

        :stability: experimental
        """
        result = self._values.get("map_role")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "AutoScalingGroupCapacityOptions(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.AutoScalingGroupOptions",
    jsii_struct_bases=[],
    name_mapping={
        "bootstrap_enabled": "bootstrapEnabled",
        "bootstrap_options": "bootstrapOptions",
        "machine_image_type": "machineImageType",
        "map_role": "mapRole",
    },
)
class AutoScalingGroupOptions:
    def __init__(
        self,
        *,
        bootstrap_enabled: typing.Optional[builtins.bool] = None,
        bootstrap_options: typing.Optional["BootstrapOptions"] = None,
        machine_image_type: typing.Optional["MachineImageType"] = None,
        map_role: typing.Optional[builtins.bool] = None,
    ) -> None:
        """(experimental) Options for adding an AutoScalingGroup as capacity.

        :param bootstrap_enabled: (experimental) Configures the EC2 user-data script for instances in this autoscaling group to bootstrap the node (invoke ``/etc/eks/bootstrap.sh``) and associate it with the EKS cluster. If you wish to provide a custom user data script, set this to ``false`` and manually invoke ``autoscalingGroup.addUserData()``. Default: true
        :param bootstrap_options: (experimental) Allows options for node bootstrapping through EC2 user data. Default: - default options
        :param machine_image_type: (experimental) Allow options to specify different machine image type. Default: MachineImageType.AMAZON_LINUX_2
        :param map_role: (experimental) Will automatically update the aws-auth ConfigMap to map the IAM instance role to RBAC. This cannot be explicitly set to ``true`` if the cluster has kubectl disabled. Default: - true if the cluster has kubectl enabled (which is the default).

        :stability: experimental
        """
        if isinstance(bootstrap_options, dict):
            bootstrap_options = BootstrapOptions(**bootstrap_options)
        self._values: typing.Dict[str, typing.Any] = {}
        if bootstrap_enabled is not None:
            self._values["bootstrap_enabled"] = bootstrap_enabled
        if bootstrap_options is not None:
            self._values["bootstrap_options"] = bootstrap_options
        if machine_image_type is not None:
            self._values["machine_image_type"] = machine_image_type
        if map_role is not None:
            self._values["map_role"] = map_role

    @builtins.property
    def bootstrap_enabled(self) -> typing.Optional[builtins.bool]:
        """(experimental) Configures the EC2 user-data script for instances in this autoscaling group to bootstrap the node (invoke ``/etc/eks/bootstrap.sh``) and associate it with the EKS cluster.

        If you wish to provide a custom user data script, set this to ``false`` and
        manually invoke ``autoscalingGroup.addUserData()``.

        :default: true

        :stability: experimental
        """
        result = self._values.get("bootstrap_enabled")
        return result

    @builtins.property
    def bootstrap_options(self) -> typing.Optional["BootstrapOptions"]:
        """(experimental) Allows options for node bootstrapping through EC2 user data.

        :default: - default options

        :stability: experimental
        """
        result = self._values.get("bootstrap_options")
        return result

    @builtins.property
    def machine_image_type(self) -> typing.Optional["MachineImageType"]:
        """(experimental) Allow options to specify different machine image type.

        :default: MachineImageType.AMAZON_LINUX_2

        :stability: experimental
        """
        result = self._values.get("machine_image_type")
        return result

    @builtins.property
    def map_role(self) -> typing.Optional[builtins.bool]:
        """(experimental) Will automatically update the aws-auth ConfigMap to map the IAM instance role to RBAC.

        This cannot be explicitly set to ``true`` if the cluster has kubectl disabled.

        :default: - true if the cluster has kubectl enabled (which is the default).

        :stability: experimental
        """
        result = self._values.get("map_role")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "AutoScalingGroupOptions(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


class AwsAuth(
    aws_cdk.core.Construct,
    metaclass=jsii.JSIIMeta,
    jsii_type="@aws-cdk/aws-eks.AwsAuth",
):
    """(experimental) Manages mapping between IAM users and roles to Kubernetes RBAC configuration.

    :see: https://docs.aws.amazon.com/en_us/eks/latest/userguide/add-user-role.html
    :stability: experimental
    """

    def __init__(
        self,
        scope: constructs.Construct,
        id: builtins.str,
        *,
        cluster: "Cluster",
    ) -> None:
        """
        :param scope: -
        :param id: -
        :param cluster: (experimental) The EKS cluster to apply this configuration to. [disable-awslint:ref-via-interface]

        :stability: experimental
        """
        props = AwsAuthProps(cluster=cluster)

        jsii.create(AwsAuth, self, [scope, id, props])

    @jsii.member(jsii_name="addAccount")
    def add_account(self, account_id: builtins.str) -> None:
        """(experimental) Additional AWS account to add to the aws-auth configmap.

        :param account_id: account number.

        :stability: experimental
        """
        return jsii.invoke(self, "addAccount", [account_id])

    @jsii.member(jsii_name="addMastersRole")
    def add_masters_role(
        self,
        role: aws_cdk.aws_iam.IRole,
        username: typing.Optional[builtins.str] = None,
    ) -> None:
        """(experimental) Adds the specified IAM role to the ``system:masters`` RBAC group, which means that anyone that can assume it will be able to administer this Kubernetes system.

        :param role: The IAM role to add.
        :param username: Optional user (defaults to the role ARN).

        :stability: experimental
        """
        return jsii.invoke(self, "addMastersRole", [role, username])

    @jsii.member(jsii_name="addRoleMapping")
    def add_role_mapping(
        self,
        role: aws_cdk.aws_iam.IRole,
        *,
        groups: typing.List[builtins.str],
        username: typing.Optional[builtins.str] = None,
    ) -> None:
        """(experimental) Adds a mapping between an IAM role to a Kubernetes user and groups.

        :param role: The IAM role to map.
        :param groups: (experimental) A list of groups within Kubernetes to which the role is mapped.
        :param username: (experimental) The user name within Kubernetes to map to the IAM role. Default: - By default, the user name is the ARN of the IAM role.

        :stability: experimental
        """
        mapping = AwsAuthMapping(groups=groups, username=username)

        return jsii.invoke(self, "addRoleMapping", [role, mapping])

    @jsii.member(jsii_name="addUserMapping")
    def add_user_mapping(
        self,
        user: aws_cdk.aws_iam.IUser,
        *,
        groups: typing.List[builtins.str],
        username: typing.Optional[builtins.str] = None,
    ) -> None:
        """(experimental) Adds a mapping between an IAM user to a Kubernetes user and groups.

        :param user: The IAM user to map.
        :param groups: (experimental) A list of groups within Kubernetes to which the role is mapped.
        :param username: (experimental) The user name within Kubernetes to map to the IAM role. Default: - By default, the user name is the ARN of the IAM role.

        :stability: experimental
        """
        mapping = AwsAuthMapping(groups=groups, username=username)

        return jsii.invoke(self, "addUserMapping", [user, mapping])


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.AwsAuthMapping",
    jsii_struct_bases=[],
    name_mapping={"groups": "groups", "username": "username"},
)
class AwsAuthMapping:
    def __init__(
        self,
        *,
        groups: typing.List[builtins.str],
        username: typing.Optional[builtins.str] = None,
    ) -> None:
        """(experimental) AwsAuth mapping.

        :param groups: (experimental) A list of groups within Kubernetes to which the role is mapped.
        :param username: (experimental) The user name within Kubernetes to map to the IAM role. Default: - By default, the user name is the ARN of the IAM role.

        :stability: experimental
        """
        self._values: typing.Dict[str, typing.Any] = {
            "groups": groups,
        }
        if username is not None:
            self._values["username"] = username

    @builtins.property
    def groups(self) -> typing.List[builtins.str]:
        """(experimental) A list of groups within Kubernetes to which the role is mapped.

        :see: https://kubernetes.io/docs/reference/access-authn-authz/rbac/#default-roles-and-role-bindings
        :stability: experimental
        """
        result = self._values.get("groups")
        assert result is not None, "Required property 'groups' is missing"
        return result

    @builtins.property
    def username(self) -> typing.Optional[builtins.str]:
        """(experimental) The user name within Kubernetes to map to the IAM role.

        :default: - By default, the user name is the ARN of the IAM role.

        :stability: experimental
        """
        result = self._values.get("username")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "AwsAuthMapping(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.AwsAuthProps",
    jsii_struct_bases=[],
    name_mapping={"cluster": "cluster"},
)
class AwsAuthProps:
    def __init__(self, *, cluster: "Cluster") -> None:
        """(experimental) Configuration props for the AwsAuth construct.

        :param cluster: (experimental) The EKS cluster to apply this configuration to. [disable-awslint:ref-via-interface]

        :stability: experimental
        """
        self._values: typing.Dict[str, typing.Any] = {
            "cluster": cluster,
        }

    @builtins.property
    def cluster(self) -> "Cluster":
        """(experimental) The EKS cluster to apply this configuration to.

        [disable-awslint:ref-via-interface]

        :stability: experimental
        """
        result = self._values.get("cluster")
        assert result is not None, "Required property 'cluster' is missing"
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "AwsAuthProps(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.BootstrapOptions",
    jsii_struct_bases=[],
    name_mapping={
        "additional_args": "additionalArgs",
        "aws_api_retry_attempts": "awsApiRetryAttempts",
        "docker_config_json": "dockerConfigJson",
        "enable_docker_bridge": "enableDockerBridge",
        "kubelet_extra_args": "kubeletExtraArgs",
        "use_max_pods": "useMaxPods",
    },
)
class BootstrapOptions:
    def __init__(
        self,
        *,
        additional_args: typing.Optional[builtins.str] = None,
        aws_api_retry_attempts: typing.Optional[jsii.Number] = None,
        docker_config_json: typing.Optional[builtins.str] = None,
        enable_docker_bridge: typing.Optional[builtins.bool] = None,
        kubelet_extra_args: typing.Optional[builtins.str] = None,
        use_max_pods: typing.Optional[builtins.bool] = None,
    ) -> None:
        """(experimental) EKS node bootstrapping options.

        :param additional_args: (experimental) Additional command line arguments to pass to the ``/etc/eks/bootstrap.sh`` command. Default: - none
        :param aws_api_retry_attempts: (experimental) Number of retry attempts for AWS API call (DescribeCluster). Default: 3
        :param docker_config_json: (experimental) The contents of the ``/etc/docker/daemon.json`` file. Useful if you want a custom config differing from the default one in the EKS AMI. Default: - none
        :param enable_docker_bridge: (experimental) Restores the docker default bridge network. Default: false
        :param kubelet_extra_args: (experimental) Extra arguments to add to the kubelet. Useful for adding labels or taints. Default: - none
        :param use_max_pods: (experimental) Sets ``--max-pods`` for the kubelet based on the capacity of the EC2 instance. Default: true

        :stability: experimental
        """
        self._values: typing.Dict[str, typing.Any] = {}
        if additional_args is not None:
            self._values["additional_args"] = additional_args
        if aws_api_retry_attempts is not None:
            self._values["aws_api_retry_attempts"] = aws_api_retry_attempts
        if docker_config_json is not None:
            self._values["docker_config_json"] = docker_config_json
        if enable_docker_bridge is not None:
            self._values["enable_docker_bridge"] = enable_docker_bridge
        if kubelet_extra_args is not None:
            self._values["kubelet_extra_args"] = kubelet_extra_args
        if use_max_pods is not None:
            self._values["use_max_pods"] = use_max_pods

    @builtins.property
    def additional_args(self) -> typing.Optional[builtins.str]:
        """(experimental) Additional command line arguments to pass to the ``/etc/eks/bootstrap.sh`` command.

        :default: - none

        :see: https://github.com/awslabs/amazon-eks-ami/blob/master/files/bootstrap.sh
        :stability: experimental
        """
        result = self._values.get("additional_args")
        return result

    @builtins.property
    def aws_api_retry_attempts(self) -> typing.Optional[jsii.Number]:
        """(experimental) Number of retry attempts for AWS API call (DescribeCluster).

        :default: 3

        :stability: experimental
        """
        result = self._values.get("aws_api_retry_attempts")
        return result

    @builtins.property
    def docker_config_json(self) -> typing.Optional[builtins.str]:
        """(experimental) The contents of the ``/etc/docker/daemon.json`` file. Useful if you want a custom config differing from the default one in the EKS AMI.

        :default: - none

        :stability: experimental
        """
        result = self._values.get("docker_config_json")
        return result

    @builtins.property
    def enable_docker_bridge(self) -> typing.Optional[builtins.bool]:
        """(experimental) Restores the docker default bridge network.

        :default: false

        :stability: experimental
        """
        result = self._values.get("enable_docker_bridge")
        return result

    @builtins.property
    def kubelet_extra_args(self) -> typing.Optional[builtins.str]:
        """(experimental) Extra arguments to add to the kubelet.

        Useful for adding labels or taints.

        :default: - none

        :stability: experimental

        Example::

            # Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
            --node - labelsfoo = bar , goo = far
        """
        result = self._values.get("kubelet_extra_args")
        return result

    @builtins.property
    def use_max_pods(self) -> typing.Optional[builtins.bool]:
        """(experimental) Sets ``--max-pods`` for the kubelet based on the capacity of the EC2 instance.

        :default: true

        :stability: experimental
        """
        result = self._values.get("use_max_pods")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "BootstrapOptions(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


@jsii.implements(aws_cdk.core.IInspectable)
class CfnCluster(
    aws_cdk.core.CfnResource,
    metaclass=jsii.JSIIMeta,
    jsii_type="@aws-cdk/aws-eks.CfnCluster",
):
    """A CloudFormation ``AWS::EKS::Cluster``.

    :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-cluster.html
    :cloudformationResource: AWS::EKS::Cluster
    """

    def __init__(
        self,
        scope: aws_cdk.core.Construct,
        id: builtins.str,
        *,
        resources_vpc_config: typing.Union["CfnCluster.ResourcesVpcConfigProperty", aws_cdk.core.IResolvable],
        role_arn: builtins.str,
        encryption_config: typing.Optional[typing.Union[aws_cdk.core.IResolvable, typing.List[typing.Union[aws_cdk.core.IResolvable, "CfnCluster.EncryptionConfigProperty"]]]] = None,
        kubernetes_network_config: typing.Optional[typing.Union[aws_cdk.core.IResolvable, "CfnCluster.KubernetesNetworkConfigProperty"]] = None,
        name: typing.Optional[builtins.str] = None,
        version: typing.Optional[builtins.str] = None,
    ) -> None:
        """Create a new ``AWS::EKS::Cluster``.

        :param scope: - scope in which this resource is defined.
        :param id: - scoped id of the resource.
        :param resources_vpc_config: ``AWS::EKS::Cluster.ResourcesVpcConfig``.
        :param role_arn: ``AWS::EKS::Cluster.RoleArn``.
        :param encryption_config: ``AWS::EKS::Cluster.EncryptionConfig``.
        :param kubernetes_network_config: ``AWS::EKS::Cluster.KubernetesNetworkConfig``.
        :param name: ``AWS::EKS::Cluster.Name``.
        :param version: ``AWS::EKS::Cluster.Version``.
        """
        props = CfnClusterProps(
            resources_vpc_config=resources_vpc_config,
            role_arn=role_arn,
            encryption_config=encryption_config,
            kubernetes_network_config=kubernetes_network_config,
            name=name,
            version=version,
        )

        jsii.create(CfnCluster, self, [scope, id, props])

    @jsii.member(jsii_name="inspect")
    def inspect(self, inspector: aws_cdk.core.TreeInspector) -> None:
        """(experimental) Examines the CloudFormation resource and discloses attributes.

        :param inspector: - tree inspector to collect and process attributes.

        :stability: experimental
        """
        return jsii.invoke(self, "inspect", [inspector])

    @jsii.member(jsii_name="renderProperties")
    def _render_properties(
        self,
        props: typing.Mapping[builtins.str, typing.Any],
    ) -> typing.Mapping[builtins.str, typing.Any]:
        """
        :param props: -
        """
        return jsii.invoke(self, "renderProperties", [props])

    @jsii.python.classproperty # type: ignore
    @jsii.member(jsii_name="CFN_RESOURCE_TYPE_NAME")
    def CFN_RESOURCE_TYPE_NAME(cls) -> builtins.str:
        """The CloudFormation resource type name for this resource class."""
        return jsii.sget(cls, "CFN_RESOURCE_TYPE_NAME")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="attrArn")
    def attr_arn(self) -> builtins.str:
        """
        :cloudformationAttribute: Arn
        """
        return jsii.get(self, "attrArn")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="attrCertificateAuthorityData")
    def attr_certificate_authority_data(self) -> builtins.str:
        """
        :cloudformationAttribute: CertificateAuthorityData
        """
        return jsii.get(self, "attrCertificateAuthorityData")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="attrClusterSecurityGroupId")
    def attr_cluster_security_group_id(self) -> builtins.str:
        """
        :cloudformationAttribute: ClusterSecurityGroupId
        """
        return jsii.get(self, "attrClusterSecurityGroupId")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="attrEncryptionConfigKeyArn")
    def attr_encryption_config_key_arn(self) -> builtins.str:
        """
        :cloudformationAttribute: EncryptionConfigKeyArn
        """
        return jsii.get(self, "attrEncryptionConfigKeyArn")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="attrEndpoint")
    def attr_endpoint(self) -> builtins.str:
        """
        :cloudformationAttribute: Endpoint
        """
        return jsii.get(self, "attrEndpoint")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="cfnProperties")
    def _cfn_properties(self) -> typing.Mapping[builtins.str, typing.Any]:
        return jsii.get(self, "cfnProperties")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="resourcesVpcConfig")
    def resources_vpc_config(
        self,
    ) -> typing.Union["CfnCluster.ResourcesVpcConfigProperty", aws_cdk.core.IResolvable]:
        """``AWS::EKS::Cluster.ResourcesVpcConfig``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-cluster.html#cfn-eks-cluster-resourcesvpcconfig
        """
        return jsii.get(self, "resourcesVpcConfig")

    @resources_vpc_config.setter # type: ignore
    def resources_vpc_config(
        self,
        value: typing.Union["CfnCluster.ResourcesVpcConfigProperty", aws_cdk.core.IResolvable],
    ) -> None:
        jsii.set(self, "resourcesVpcConfig", value)

    @builtins.property # type: ignore
    @jsii.member(jsii_name="roleArn")
    def role_arn(self) -> builtins.str:
        """``AWS::EKS::Cluster.RoleArn``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-cluster.html#cfn-eks-cluster-rolearn
        """
        return jsii.get(self, "roleArn")

    @role_arn.setter # type: ignore
    def role_arn(self, value: builtins.str) -> None:
        jsii.set(self, "roleArn", value)

    @builtins.property # type: ignore
    @jsii.member(jsii_name="encryptionConfig")
    def encryption_config(
        self,
    ) -> typing.Optional[typing.Union[aws_cdk.core.IResolvable, typing.List[typing.Union[aws_cdk.core.IResolvable, "CfnCluster.EncryptionConfigProperty"]]]]:
        """``AWS::EKS::Cluster.EncryptionConfig``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-cluster.html#cfn-eks-cluster-encryptionconfig
        """
        return jsii.get(self, "encryptionConfig")

    @encryption_config.setter # type: ignore
    def encryption_config(
        self,
        value: typing.Optional[typing.Union[aws_cdk.core.IResolvable, typing.List[typing.Union[aws_cdk.core.IResolvable, "CfnCluster.EncryptionConfigProperty"]]]],
    ) -> None:
        jsii.set(self, "encryptionConfig", value)

    @builtins.property # type: ignore
    @jsii.member(jsii_name="kubernetesNetworkConfig")
    def kubernetes_network_config(
        self,
    ) -> typing.Optional[typing.Union[aws_cdk.core.IResolvable, "CfnCluster.KubernetesNetworkConfigProperty"]]:
        """``AWS::EKS::Cluster.KubernetesNetworkConfig``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-cluster.html#cfn-eks-cluster-kubernetesnetworkconfig
        """
        return jsii.get(self, "kubernetesNetworkConfig")

    @kubernetes_network_config.setter # type: ignore
    def kubernetes_network_config(
        self,
        value: typing.Optional[typing.Union[aws_cdk.core.IResolvable, "CfnCluster.KubernetesNetworkConfigProperty"]],
    ) -> None:
        jsii.set(self, "kubernetesNetworkConfig", value)

    @builtins.property # type: ignore
    @jsii.member(jsii_name="name")
    def name(self) -> typing.Optional[builtins.str]:
        """``AWS::EKS::Cluster.Name``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-cluster.html#cfn-eks-cluster-name
        """
        return jsii.get(self, "name")

    @name.setter # type: ignore
    def name(self, value: typing.Optional[builtins.str]) -> None:
        jsii.set(self, "name", value)

    @builtins.property # type: ignore
    @jsii.member(jsii_name="version")
    def version(self) -> typing.Optional[builtins.str]:
        """``AWS::EKS::Cluster.Version``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-cluster.html#cfn-eks-cluster-version
        """
        return jsii.get(self, "version")

    @version.setter # type: ignore
    def version(self, value: typing.Optional[builtins.str]) -> None:
        jsii.set(self, "version", value)

    @jsii.data_type(
        jsii_type="@aws-cdk/aws-eks.CfnCluster.EncryptionConfigProperty",
        jsii_struct_bases=[],
        name_mapping={"provider": "provider", "resources": "resources"},
    )
    class EncryptionConfigProperty:
        def __init__(
            self,
            *,
            provider: typing.Optional[typing.Union[aws_cdk.core.IResolvable, "CfnCluster.ProviderProperty"]] = None,
            resources: typing.Optional[typing.List[builtins.str]] = None,
        ) -> None:
            """
            :param provider: ``CfnCluster.EncryptionConfigProperty.Provider``.
            :param resources: ``CfnCluster.EncryptionConfigProperty.Resources``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-cluster-encryptionconfig.html
            """
            self._values: typing.Dict[str, typing.Any] = {}
            if provider is not None:
                self._values["provider"] = provider
            if resources is not None:
                self._values["resources"] = resources

        @builtins.property
        def provider(
            self,
        ) -> typing.Optional[typing.Union[aws_cdk.core.IResolvable, "CfnCluster.ProviderProperty"]]:
            """``CfnCluster.EncryptionConfigProperty.Provider``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-cluster-encryptionconfig.html#cfn-eks-cluster-encryptionconfig-provider
            """
            result = self._values.get("provider")
            return result

        @builtins.property
        def resources(self) -> typing.Optional[typing.List[builtins.str]]:
            """``CfnCluster.EncryptionConfigProperty.Resources``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-cluster-encryptionconfig.html#cfn-eks-cluster-encryptionconfig-resources
            """
            result = self._values.get("resources")
            return result

        def __eq__(self, rhs: typing.Any) -> builtins.bool:
            return isinstance(rhs, self.__class__) and rhs._values == self._values

        def __ne__(self, rhs: typing.Any) -> builtins.bool:
            return not (rhs == self)

        def __repr__(self) -> str:
            return "EncryptionConfigProperty(%s)" % ", ".join(
                k + "=" + repr(v) for k, v in self._values.items()
            )

    @jsii.data_type(
        jsii_type="@aws-cdk/aws-eks.CfnCluster.KubernetesNetworkConfigProperty",
        jsii_struct_bases=[],
        name_mapping={"service_ipv4_cidr": "serviceIpv4Cidr"},
    )
    class KubernetesNetworkConfigProperty:
        def __init__(
            self,
            *,
            service_ipv4_cidr: typing.Optional[builtins.str] = None,
        ) -> None:
            """
            :param service_ipv4_cidr: ``CfnCluster.KubernetesNetworkConfigProperty.ServiceIpv4Cidr``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-cluster-kubernetesnetworkconfig.html
            """
            self._values: typing.Dict[str, typing.Any] = {}
            if service_ipv4_cidr is not None:
                self._values["service_ipv4_cidr"] = service_ipv4_cidr

        @builtins.property
        def service_ipv4_cidr(self) -> typing.Optional[builtins.str]:
            """``CfnCluster.KubernetesNetworkConfigProperty.ServiceIpv4Cidr``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-cluster-kubernetesnetworkconfig.html#cfn-eks-cluster-kubernetesnetworkconfig-serviceipv4cidr
            """
            result = self._values.get("service_ipv4_cidr")
            return result

        def __eq__(self, rhs: typing.Any) -> builtins.bool:
            return isinstance(rhs, self.__class__) and rhs._values == self._values

        def __ne__(self, rhs: typing.Any) -> builtins.bool:
            return not (rhs == self)

        def __repr__(self) -> str:
            return "KubernetesNetworkConfigProperty(%s)" % ", ".join(
                k + "=" + repr(v) for k, v in self._values.items()
            )

    @jsii.data_type(
        jsii_type="@aws-cdk/aws-eks.CfnCluster.ProviderProperty",
        jsii_struct_bases=[],
        name_mapping={"key_arn": "keyArn"},
    )
    class ProviderProperty:
        def __init__(self, *, key_arn: typing.Optional[builtins.str] = None) -> None:
            """
            :param key_arn: ``CfnCluster.ProviderProperty.KeyArn``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-cluster-provider.html
            """
            self._values: typing.Dict[str, typing.Any] = {}
            if key_arn is not None:
                self._values["key_arn"] = key_arn

        @builtins.property
        def key_arn(self) -> typing.Optional[builtins.str]:
            """``CfnCluster.ProviderProperty.KeyArn``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-cluster-provider.html#cfn-eks-cluster-provider-keyarn
            """
            result = self._values.get("key_arn")
            return result

        def __eq__(self, rhs: typing.Any) -> builtins.bool:
            return isinstance(rhs, self.__class__) and rhs._values == self._values

        def __ne__(self, rhs: typing.Any) -> builtins.bool:
            return not (rhs == self)

        def __repr__(self) -> str:
            return "ProviderProperty(%s)" % ", ".join(
                k + "=" + repr(v) for k, v in self._values.items()
            )

    @jsii.data_type(
        jsii_type="@aws-cdk/aws-eks.CfnCluster.ResourcesVpcConfigProperty",
        jsii_struct_bases=[],
        name_mapping={
            "subnet_ids": "subnetIds",
            "security_group_ids": "securityGroupIds",
        },
    )
    class ResourcesVpcConfigProperty:
        def __init__(
            self,
            *,
            subnet_ids: typing.List[builtins.str],
            security_group_ids: typing.Optional[typing.List[builtins.str]] = None,
        ) -> None:
            """
            :param subnet_ids: ``CfnCluster.ResourcesVpcConfigProperty.SubnetIds``.
            :param security_group_ids: ``CfnCluster.ResourcesVpcConfigProperty.SecurityGroupIds``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-cluster-resourcesvpcconfig.html
            """
            self._values: typing.Dict[str, typing.Any] = {
                "subnet_ids": subnet_ids,
            }
            if security_group_ids is not None:
                self._values["security_group_ids"] = security_group_ids

        @builtins.property
        def subnet_ids(self) -> typing.List[builtins.str]:
            """``CfnCluster.ResourcesVpcConfigProperty.SubnetIds``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-cluster-resourcesvpcconfig.html#cfn-eks-cluster-resourcesvpcconfig-subnetids
            """
            result = self._values.get("subnet_ids")
            assert result is not None, "Required property 'subnet_ids' is missing"
            return result

        @builtins.property
        def security_group_ids(self) -> typing.Optional[typing.List[builtins.str]]:
            """``CfnCluster.ResourcesVpcConfigProperty.SecurityGroupIds``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-cluster-resourcesvpcconfig.html#cfn-eks-cluster-resourcesvpcconfig-securitygroupids
            """
            result = self._values.get("security_group_ids")
            return result

        def __eq__(self, rhs: typing.Any) -> builtins.bool:
            return isinstance(rhs, self.__class__) and rhs._values == self._values

        def __ne__(self, rhs: typing.Any) -> builtins.bool:
            return not (rhs == self)

        def __repr__(self) -> str:
            return "ResourcesVpcConfigProperty(%s)" % ", ".join(
                k + "=" + repr(v) for k, v in self._values.items()
            )


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.CfnClusterProps",
    jsii_struct_bases=[],
    name_mapping={
        "resources_vpc_config": "resourcesVpcConfig",
        "role_arn": "roleArn",
        "encryption_config": "encryptionConfig",
        "kubernetes_network_config": "kubernetesNetworkConfig",
        "name": "name",
        "version": "version",
    },
)
class CfnClusterProps:
    def __init__(
        self,
        *,
        resources_vpc_config: typing.Union[CfnCluster.ResourcesVpcConfigProperty, aws_cdk.core.IResolvable],
        role_arn: builtins.str,
        encryption_config: typing.Optional[typing.Union[aws_cdk.core.IResolvable, typing.List[typing.Union[aws_cdk.core.IResolvable, CfnCluster.EncryptionConfigProperty]]]] = None,
        kubernetes_network_config: typing.Optional[typing.Union[aws_cdk.core.IResolvable, CfnCluster.KubernetesNetworkConfigProperty]] = None,
        name: typing.Optional[builtins.str] = None,
        version: typing.Optional[builtins.str] = None,
    ) -> None:
        """Properties for defining a ``AWS::EKS::Cluster``.

        :param resources_vpc_config: ``AWS::EKS::Cluster.ResourcesVpcConfig``.
        :param role_arn: ``AWS::EKS::Cluster.RoleArn``.
        :param encryption_config: ``AWS::EKS::Cluster.EncryptionConfig``.
        :param kubernetes_network_config: ``AWS::EKS::Cluster.KubernetesNetworkConfig``.
        :param name: ``AWS::EKS::Cluster.Name``.
        :param version: ``AWS::EKS::Cluster.Version``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-cluster.html
        """
        self._values: typing.Dict[str, typing.Any] = {
            "resources_vpc_config": resources_vpc_config,
            "role_arn": role_arn,
        }
        if encryption_config is not None:
            self._values["encryption_config"] = encryption_config
        if kubernetes_network_config is not None:
            self._values["kubernetes_network_config"] = kubernetes_network_config
        if name is not None:
            self._values["name"] = name
        if version is not None:
            self._values["version"] = version

    @builtins.property
    def resources_vpc_config(
        self,
    ) -> typing.Union[CfnCluster.ResourcesVpcConfigProperty, aws_cdk.core.IResolvable]:
        """``AWS::EKS::Cluster.ResourcesVpcConfig``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-cluster.html#cfn-eks-cluster-resourcesvpcconfig
        """
        result = self._values.get("resources_vpc_config")
        assert result is not None, "Required property 'resources_vpc_config' is missing"
        return result

    @builtins.property
    def role_arn(self) -> builtins.str:
        """``AWS::EKS::Cluster.RoleArn``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-cluster.html#cfn-eks-cluster-rolearn
        """
        result = self._values.get("role_arn")
        assert result is not None, "Required property 'role_arn' is missing"
        return result

    @builtins.property
    def encryption_config(
        self,
    ) -> typing.Optional[typing.Union[aws_cdk.core.IResolvable, typing.List[typing.Union[aws_cdk.core.IResolvable, CfnCluster.EncryptionConfigProperty]]]]:
        """``AWS::EKS::Cluster.EncryptionConfig``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-cluster.html#cfn-eks-cluster-encryptionconfig
        """
        result = self._values.get("encryption_config")
        return result

    @builtins.property
    def kubernetes_network_config(
        self,
    ) -> typing.Optional[typing.Union[aws_cdk.core.IResolvable, CfnCluster.KubernetesNetworkConfigProperty]]:
        """``AWS::EKS::Cluster.KubernetesNetworkConfig``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-cluster.html#cfn-eks-cluster-kubernetesnetworkconfig
        """
        result = self._values.get("kubernetes_network_config")
        return result

    @builtins.property
    def name(self) -> typing.Optional[builtins.str]:
        """``AWS::EKS::Cluster.Name``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-cluster.html#cfn-eks-cluster-name
        """
        result = self._values.get("name")
        return result

    @builtins.property
    def version(self) -> typing.Optional[builtins.str]:
        """``AWS::EKS::Cluster.Version``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-cluster.html#cfn-eks-cluster-version
        """
        result = self._values.get("version")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "CfnClusterProps(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


@jsii.implements(aws_cdk.core.IInspectable)
class CfnFargateProfile(
    aws_cdk.core.CfnResource,
    metaclass=jsii.JSIIMeta,
    jsii_type="@aws-cdk/aws-eks.CfnFargateProfile",
):
    """A CloudFormation ``AWS::EKS::FargateProfile``.

    :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-fargateprofile.html
    :cloudformationResource: AWS::EKS::FargateProfile
    """

    def __init__(
        self,
        scope: aws_cdk.core.Construct,
        id: builtins.str,
        *,
        cluster_name: builtins.str,
        pod_execution_role_arn: builtins.str,
        selectors: typing.Union[aws_cdk.core.IResolvable, typing.List[typing.Union[aws_cdk.core.IResolvable, "CfnFargateProfile.SelectorProperty"]]],
        fargate_profile_name: typing.Optional[builtins.str] = None,
        subnets: typing.Optional[typing.List[builtins.str]] = None,
        tags: typing.Optional[typing.List[aws_cdk.core.CfnTag]] = None,
    ) -> None:
        """Create a new ``AWS::EKS::FargateProfile``.

        :param scope: - scope in which this resource is defined.
        :param id: - scoped id of the resource.
        :param cluster_name: ``AWS::EKS::FargateProfile.ClusterName``.
        :param pod_execution_role_arn: ``AWS::EKS::FargateProfile.PodExecutionRoleArn``.
        :param selectors: ``AWS::EKS::FargateProfile.Selectors``.
        :param fargate_profile_name: ``AWS::EKS::FargateProfile.FargateProfileName``.
        :param subnets: ``AWS::EKS::FargateProfile.Subnets``.
        :param tags: ``AWS::EKS::FargateProfile.Tags``.
        """
        props = CfnFargateProfileProps(
            cluster_name=cluster_name,
            pod_execution_role_arn=pod_execution_role_arn,
            selectors=selectors,
            fargate_profile_name=fargate_profile_name,
            subnets=subnets,
            tags=tags,
        )

        jsii.create(CfnFargateProfile, self, [scope, id, props])

    @jsii.member(jsii_name="inspect")
    def inspect(self, inspector: aws_cdk.core.TreeInspector) -> None:
        """(experimental) Examines the CloudFormation resource and discloses attributes.

        :param inspector: - tree inspector to collect and process attributes.

        :stability: experimental
        """
        return jsii.invoke(self, "inspect", [inspector])

    @jsii.member(jsii_name="renderProperties")
    def _render_properties(
        self,
        props: typing.Mapping[builtins.str, typing.Any],
    ) -> typing.Mapping[builtins.str, typing.Any]:
        """
        :param props: -
        """
        return jsii.invoke(self, "renderProperties", [props])

    @jsii.python.classproperty # type: ignore
    @jsii.member(jsii_name="CFN_RESOURCE_TYPE_NAME")
    def CFN_RESOURCE_TYPE_NAME(cls) -> builtins.str:
        """The CloudFormation resource type name for this resource class."""
        return jsii.sget(cls, "CFN_RESOURCE_TYPE_NAME")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="attrArn")
    def attr_arn(self) -> builtins.str:
        """
        :cloudformationAttribute: Arn
        """
        return jsii.get(self, "attrArn")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="cfnProperties")
    def _cfn_properties(self) -> typing.Mapping[builtins.str, typing.Any]:
        return jsii.get(self, "cfnProperties")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="tags")
    def tags(self) -> aws_cdk.core.TagManager:
        """``AWS::EKS::FargateProfile.Tags``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-fargateprofile.html#cfn-eks-fargateprofile-tags
        """
        return jsii.get(self, "tags")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterName")
    def cluster_name(self) -> builtins.str:
        """``AWS::EKS::FargateProfile.ClusterName``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-fargateprofile.html#cfn-eks-fargateprofile-clustername
        """
        return jsii.get(self, "clusterName")

    @cluster_name.setter # type: ignore
    def cluster_name(self, value: builtins.str) -> None:
        jsii.set(self, "clusterName", value)

    @builtins.property # type: ignore
    @jsii.member(jsii_name="podExecutionRoleArn")
    def pod_execution_role_arn(self) -> builtins.str:
        """``AWS::EKS::FargateProfile.PodExecutionRoleArn``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-fargateprofile.html#cfn-eks-fargateprofile-podexecutionrolearn
        """
        return jsii.get(self, "podExecutionRoleArn")

    @pod_execution_role_arn.setter # type: ignore
    def pod_execution_role_arn(self, value: builtins.str) -> None:
        jsii.set(self, "podExecutionRoleArn", value)

    @builtins.property # type: ignore
    @jsii.member(jsii_name="selectors")
    def selectors(
        self,
    ) -> typing.Union[aws_cdk.core.IResolvable, typing.List[typing.Union[aws_cdk.core.IResolvable, "CfnFargateProfile.SelectorProperty"]]]:
        """``AWS::EKS::FargateProfile.Selectors``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-fargateprofile.html#cfn-eks-fargateprofile-selectors
        """
        return jsii.get(self, "selectors")

    @selectors.setter # type: ignore
    def selectors(
        self,
        value: typing.Union[aws_cdk.core.IResolvable, typing.List[typing.Union[aws_cdk.core.IResolvable, "CfnFargateProfile.SelectorProperty"]]],
    ) -> None:
        jsii.set(self, "selectors", value)

    @builtins.property # type: ignore
    @jsii.member(jsii_name="fargateProfileName")
    def fargate_profile_name(self) -> typing.Optional[builtins.str]:
        """``AWS::EKS::FargateProfile.FargateProfileName``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-fargateprofile.html#cfn-eks-fargateprofile-fargateprofilename
        """
        return jsii.get(self, "fargateProfileName")

    @fargate_profile_name.setter # type: ignore
    def fargate_profile_name(self, value: typing.Optional[builtins.str]) -> None:
        jsii.set(self, "fargateProfileName", value)

    @builtins.property # type: ignore
    @jsii.member(jsii_name="subnets")
    def subnets(self) -> typing.Optional[typing.List[builtins.str]]:
        """``AWS::EKS::FargateProfile.Subnets``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-fargateprofile.html#cfn-eks-fargateprofile-subnets
        """
        return jsii.get(self, "subnets")

    @subnets.setter # type: ignore
    def subnets(self, value: typing.Optional[typing.List[builtins.str]]) -> None:
        jsii.set(self, "subnets", value)

    @jsii.data_type(
        jsii_type="@aws-cdk/aws-eks.CfnFargateProfile.LabelProperty",
        jsii_struct_bases=[],
        name_mapping={"key": "key", "value": "value"},
    )
    class LabelProperty:
        def __init__(self, *, key: builtins.str, value: builtins.str) -> None:
            """
            :param key: ``CfnFargateProfile.LabelProperty.Key``.
            :param value: ``CfnFargateProfile.LabelProperty.Value``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-fargateprofile-label.html
            """
            self._values: typing.Dict[str, typing.Any] = {
                "key": key,
                "value": value,
            }

        @builtins.property
        def key(self) -> builtins.str:
            """``CfnFargateProfile.LabelProperty.Key``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-fargateprofile-label.html#cfn-eks-fargateprofile-label-key
            """
            result = self._values.get("key")
            assert result is not None, "Required property 'key' is missing"
            return result

        @builtins.property
        def value(self) -> builtins.str:
            """``CfnFargateProfile.LabelProperty.Value``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-fargateprofile-label.html#cfn-eks-fargateprofile-label-value
            """
            result = self._values.get("value")
            assert result is not None, "Required property 'value' is missing"
            return result

        def __eq__(self, rhs: typing.Any) -> builtins.bool:
            return isinstance(rhs, self.__class__) and rhs._values == self._values

        def __ne__(self, rhs: typing.Any) -> builtins.bool:
            return not (rhs == self)

        def __repr__(self) -> str:
            return "LabelProperty(%s)" % ", ".join(
                k + "=" + repr(v) for k, v in self._values.items()
            )

    @jsii.data_type(
        jsii_type="@aws-cdk/aws-eks.CfnFargateProfile.SelectorProperty",
        jsii_struct_bases=[],
        name_mapping={"namespace": "namespace", "labels": "labels"},
    )
    class SelectorProperty:
        def __init__(
            self,
            *,
            namespace: builtins.str,
            labels: typing.Optional[typing.Union[aws_cdk.core.IResolvable, typing.List[typing.Union[aws_cdk.core.IResolvable, "CfnFargateProfile.LabelProperty"]]]] = None,
        ) -> None:
            """
            :param namespace: ``CfnFargateProfile.SelectorProperty.Namespace``.
            :param labels: ``CfnFargateProfile.SelectorProperty.Labels``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-fargateprofile-selector.html
            """
            self._values: typing.Dict[str, typing.Any] = {
                "namespace": namespace,
            }
            if labels is not None:
                self._values["labels"] = labels

        @builtins.property
        def namespace(self) -> builtins.str:
            """``CfnFargateProfile.SelectorProperty.Namespace``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-fargateprofile-selector.html#cfn-eks-fargateprofile-selector-namespace
            """
            result = self._values.get("namespace")
            assert result is not None, "Required property 'namespace' is missing"
            return result

        @builtins.property
        def labels(
            self,
        ) -> typing.Optional[typing.Union[aws_cdk.core.IResolvable, typing.List[typing.Union[aws_cdk.core.IResolvable, "CfnFargateProfile.LabelProperty"]]]]:
            """``CfnFargateProfile.SelectorProperty.Labels``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-fargateprofile-selector.html#cfn-eks-fargateprofile-selector-labels
            """
            result = self._values.get("labels")
            return result

        def __eq__(self, rhs: typing.Any) -> builtins.bool:
            return isinstance(rhs, self.__class__) and rhs._values == self._values

        def __ne__(self, rhs: typing.Any) -> builtins.bool:
            return not (rhs == self)

        def __repr__(self) -> str:
            return "SelectorProperty(%s)" % ", ".join(
                k + "=" + repr(v) for k, v in self._values.items()
            )


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.CfnFargateProfileProps",
    jsii_struct_bases=[],
    name_mapping={
        "cluster_name": "clusterName",
        "pod_execution_role_arn": "podExecutionRoleArn",
        "selectors": "selectors",
        "fargate_profile_name": "fargateProfileName",
        "subnets": "subnets",
        "tags": "tags",
    },
)
class CfnFargateProfileProps:
    def __init__(
        self,
        *,
        cluster_name: builtins.str,
        pod_execution_role_arn: builtins.str,
        selectors: typing.Union[aws_cdk.core.IResolvable, typing.List[typing.Union[aws_cdk.core.IResolvable, CfnFargateProfile.SelectorProperty]]],
        fargate_profile_name: typing.Optional[builtins.str] = None,
        subnets: typing.Optional[typing.List[builtins.str]] = None,
        tags: typing.Optional[typing.List[aws_cdk.core.CfnTag]] = None,
    ) -> None:
        """Properties for defining a ``AWS::EKS::FargateProfile``.

        :param cluster_name: ``AWS::EKS::FargateProfile.ClusterName``.
        :param pod_execution_role_arn: ``AWS::EKS::FargateProfile.PodExecutionRoleArn``.
        :param selectors: ``AWS::EKS::FargateProfile.Selectors``.
        :param fargate_profile_name: ``AWS::EKS::FargateProfile.FargateProfileName``.
        :param subnets: ``AWS::EKS::FargateProfile.Subnets``.
        :param tags: ``AWS::EKS::FargateProfile.Tags``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-fargateprofile.html
        """
        self._values: typing.Dict[str, typing.Any] = {
            "cluster_name": cluster_name,
            "pod_execution_role_arn": pod_execution_role_arn,
            "selectors": selectors,
        }
        if fargate_profile_name is not None:
            self._values["fargate_profile_name"] = fargate_profile_name
        if subnets is not None:
            self._values["subnets"] = subnets
        if tags is not None:
            self._values["tags"] = tags

    @builtins.property
    def cluster_name(self) -> builtins.str:
        """``AWS::EKS::FargateProfile.ClusterName``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-fargateprofile.html#cfn-eks-fargateprofile-clustername
        """
        result = self._values.get("cluster_name")
        assert result is not None, "Required property 'cluster_name' is missing"
        return result

    @builtins.property
    def pod_execution_role_arn(self) -> builtins.str:
        """``AWS::EKS::FargateProfile.PodExecutionRoleArn``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-fargateprofile.html#cfn-eks-fargateprofile-podexecutionrolearn
        """
        result = self._values.get("pod_execution_role_arn")
        assert result is not None, "Required property 'pod_execution_role_arn' is missing"
        return result

    @builtins.property
    def selectors(
        self,
    ) -> typing.Union[aws_cdk.core.IResolvable, typing.List[typing.Union[aws_cdk.core.IResolvable, CfnFargateProfile.SelectorProperty]]]:
        """``AWS::EKS::FargateProfile.Selectors``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-fargateprofile.html#cfn-eks-fargateprofile-selectors
        """
        result = self._values.get("selectors")
        assert result is not None, "Required property 'selectors' is missing"
        return result

    @builtins.property
    def fargate_profile_name(self) -> typing.Optional[builtins.str]:
        """``AWS::EKS::FargateProfile.FargateProfileName``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-fargateprofile.html#cfn-eks-fargateprofile-fargateprofilename
        """
        result = self._values.get("fargate_profile_name")
        return result

    @builtins.property
    def subnets(self) -> typing.Optional[typing.List[builtins.str]]:
        """``AWS::EKS::FargateProfile.Subnets``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-fargateprofile.html#cfn-eks-fargateprofile-subnets
        """
        result = self._values.get("subnets")
        return result

    @builtins.property
    def tags(self) -> typing.Optional[typing.List[aws_cdk.core.CfnTag]]:
        """``AWS::EKS::FargateProfile.Tags``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-fargateprofile.html#cfn-eks-fargateprofile-tags
        """
        result = self._values.get("tags")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "CfnFargateProfileProps(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


@jsii.implements(aws_cdk.core.IInspectable)
class CfnNodegroup(
    aws_cdk.core.CfnResource,
    metaclass=jsii.JSIIMeta,
    jsii_type="@aws-cdk/aws-eks.CfnNodegroup",
):
    """A CloudFormation ``AWS::EKS::Nodegroup``.

    :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html
    :cloudformationResource: AWS::EKS::Nodegroup
    """

    def __init__(
        self,
        scope: aws_cdk.core.Construct,
        id: builtins.str,
        *,
        cluster_name: builtins.str,
        node_role: builtins.str,
        subnets: typing.List[builtins.str],
        ami_type: typing.Optional[builtins.str] = None,
        disk_size: typing.Optional[jsii.Number] = None,
        force_update_enabled: typing.Optional[typing.Union[builtins.bool, aws_cdk.core.IResolvable]] = None,
        instance_types: typing.Optional[typing.List[builtins.str]] = None,
        labels: typing.Any = None,
        launch_template: typing.Optional[typing.Union[aws_cdk.core.IResolvable, "CfnNodegroup.LaunchTemplateSpecificationProperty"]] = None,
        nodegroup_name: typing.Optional[builtins.str] = None,
        release_version: typing.Optional[builtins.str] = None,
        remote_access: typing.Optional[typing.Union[aws_cdk.core.IResolvable, "CfnNodegroup.RemoteAccessProperty"]] = None,
        scaling_config: typing.Optional[typing.Union[aws_cdk.core.IResolvable, "CfnNodegroup.ScalingConfigProperty"]] = None,
        tags: typing.Any = None,
        version: typing.Optional[builtins.str] = None,
    ) -> None:
        """Create a new ``AWS::EKS::Nodegroup``.

        :param scope: - scope in which this resource is defined.
        :param id: - scoped id of the resource.
        :param cluster_name: ``AWS::EKS::Nodegroup.ClusterName``.
        :param node_role: ``AWS::EKS::Nodegroup.NodeRole``.
        :param subnets: ``AWS::EKS::Nodegroup.Subnets``.
        :param ami_type: ``AWS::EKS::Nodegroup.AmiType``.
        :param disk_size: ``AWS::EKS::Nodegroup.DiskSize``.
        :param force_update_enabled: ``AWS::EKS::Nodegroup.ForceUpdateEnabled``.
        :param instance_types: ``AWS::EKS::Nodegroup.InstanceTypes``.
        :param labels: ``AWS::EKS::Nodegroup.Labels``.
        :param launch_template: ``AWS::EKS::Nodegroup.LaunchTemplate``.
        :param nodegroup_name: ``AWS::EKS::Nodegroup.NodegroupName``.
        :param release_version: ``AWS::EKS::Nodegroup.ReleaseVersion``.
        :param remote_access: ``AWS::EKS::Nodegroup.RemoteAccess``.
        :param scaling_config: ``AWS::EKS::Nodegroup.ScalingConfig``.
        :param tags: ``AWS::EKS::Nodegroup.Tags``.
        :param version: ``AWS::EKS::Nodegroup.Version``.
        """
        props = CfnNodegroupProps(
            cluster_name=cluster_name,
            node_role=node_role,
            subnets=subnets,
            ami_type=ami_type,
            disk_size=disk_size,
            force_update_enabled=force_update_enabled,
            instance_types=instance_types,
            labels=labels,
            launch_template=launch_template,
            nodegroup_name=nodegroup_name,
            release_version=release_version,
            remote_access=remote_access,
            scaling_config=scaling_config,
            tags=tags,
            version=version,
        )

        jsii.create(CfnNodegroup, self, [scope, id, props])

    @jsii.member(jsii_name="inspect")
    def inspect(self, inspector: aws_cdk.core.TreeInspector) -> None:
        """(experimental) Examines the CloudFormation resource and discloses attributes.

        :param inspector: - tree inspector to collect and process attributes.

        :stability: experimental
        """
        return jsii.invoke(self, "inspect", [inspector])

    @jsii.member(jsii_name="renderProperties")
    def _render_properties(
        self,
        props: typing.Mapping[builtins.str, typing.Any],
    ) -> typing.Mapping[builtins.str, typing.Any]:
        """
        :param props: -
        """
        return jsii.invoke(self, "renderProperties", [props])

    @jsii.python.classproperty # type: ignore
    @jsii.member(jsii_name="CFN_RESOURCE_TYPE_NAME")
    def CFN_RESOURCE_TYPE_NAME(cls) -> builtins.str:
        """The CloudFormation resource type name for this resource class."""
        return jsii.sget(cls, "CFN_RESOURCE_TYPE_NAME")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="attrArn")
    def attr_arn(self) -> builtins.str:
        """
        :cloudformationAttribute: Arn
        """
        return jsii.get(self, "attrArn")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="attrClusterName")
    def attr_cluster_name(self) -> builtins.str:
        """
        :cloudformationAttribute: ClusterName
        """
        return jsii.get(self, "attrClusterName")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="attrNodegroupName")
    def attr_nodegroup_name(self) -> builtins.str:
        """
        :cloudformationAttribute: NodegroupName
        """
        return jsii.get(self, "attrNodegroupName")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="cfnProperties")
    def _cfn_properties(self) -> typing.Mapping[builtins.str, typing.Any]:
        return jsii.get(self, "cfnProperties")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="tags")
    def tags(self) -> aws_cdk.core.TagManager:
        """``AWS::EKS::Nodegroup.Tags``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-tags
        """
        return jsii.get(self, "tags")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterName")
    def cluster_name(self) -> builtins.str:
        """``AWS::EKS::Nodegroup.ClusterName``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-clustername
        """
        return jsii.get(self, "clusterName")

    @cluster_name.setter # type: ignore
    def cluster_name(self, value: builtins.str) -> None:
        jsii.set(self, "clusterName", value)

    @builtins.property # type: ignore
    @jsii.member(jsii_name="labels")
    def labels(self) -> typing.Any:
        """``AWS::EKS::Nodegroup.Labels``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-labels
        """
        return jsii.get(self, "labels")

    @labels.setter # type: ignore
    def labels(self, value: typing.Any) -> None:
        jsii.set(self, "labels", value)

    @builtins.property # type: ignore
    @jsii.member(jsii_name="nodeRole")
    def node_role(self) -> builtins.str:
        """``AWS::EKS::Nodegroup.NodeRole``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-noderole
        """
        return jsii.get(self, "nodeRole")

    @node_role.setter # type: ignore
    def node_role(self, value: builtins.str) -> None:
        jsii.set(self, "nodeRole", value)

    @builtins.property # type: ignore
    @jsii.member(jsii_name="subnets")
    def subnets(self) -> typing.List[builtins.str]:
        """``AWS::EKS::Nodegroup.Subnets``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-subnets
        """
        return jsii.get(self, "subnets")

    @subnets.setter # type: ignore
    def subnets(self, value: typing.List[builtins.str]) -> None:
        jsii.set(self, "subnets", value)

    @builtins.property # type: ignore
    @jsii.member(jsii_name="amiType")
    def ami_type(self) -> typing.Optional[builtins.str]:
        """``AWS::EKS::Nodegroup.AmiType``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-amitype
        """
        return jsii.get(self, "amiType")

    @ami_type.setter # type: ignore
    def ami_type(self, value: typing.Optional[builtins.str]) -> None:
        jsii.set(self, "amiType", value)

    @builtins.property # type: ignore
    @jsii.member(jsii_name="diskSize")
    def disk_size(self) -> typing.Optional[jsii.Number]:
        """``AWS::EKS::Nodegroup.DiskSize``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-disksize
        """
        return jsii.get(self, "diskSize")

    @disk_size.setter # type: ignore
    def disk_size(self, value: typing.Optional[jsii.Number]) -> None:
        jsii.set(self, "diskSize", value)

    @builtins.property # type: ignore
    @jsii.member(jsii_name="forceUpdateEnabled")
    def force_update_enabled(
        self,
    ) -> typing.Optional[typing.Union[builtins.bool, aws_cdk.core.IResolvable]]:
        """``AWS::EKS::Nodegroup.ForceUpdateEnabled``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-forceupdateenabled
        """
        return jsii.get(self, "forceUpdateEnabled")

    @force_update_enabled.setter # type: ignore
    def force_update_enabled(
        self,
        value: typing.Optional[typing.Union[builtins.bool, aws_cdk.core.IResolvable]],
    ) -> None:
        jsii.set(self, "forceUpdateEnabled", value)

    @builtins.property # type: ignore
    @jsii.member(jsii_name="instanceTypes")
    def instance_types(self) -> typing.Optional[typing.List[builtins.str]]:
        """``AWS::EKS::Nodegroup.InstanceTypes``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-instancetypes
        """
        return jsii.get(self, "instanceTypes")

    @instance_types.setter # type: ignore
    def instance_types(self, value: typing.Optional[typing.List[builtins.str]]) -> None:
        jsii.set(self, "instanceTypes", value)

    @builtins.property # type: ignore
    @jsii.member(jsii_name="launchTemplate")
    def launch_template(
        self,
    ) -> typing.Optional[typing.Union[aws_cdk.core.IResolvable, "CfnNodegroup.LaunchTemplateSpecificationProperty"]]:
        """``AWS::EKS::Nodegroup.LaunchTemplate``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-launchtemplate
        """
        return jsii.get(self, "launchTemplate")

    @launch_template.setter # type: ignore
    def launch_template(
        self,
        value: typing.Optional[typing.Union[aws_cdk.core.IResolvable, "CfnNodegroup.LaunchTemplateSpecificationProperty"]],
    ) -> None:
        jsii.set(self, "launchTemplate", value)

    @builtins.property # type: ignore
    @jsii.member(jsii_name="nodegroupName")
    def nodegroup_name(self) -> typing.Optional[builtins.str]:
        """``AWS::EKS::Nodegroup.NodegroupName``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-nodegroupname
        """
        return jsii.get(self, "nodegroupName")

    @nodegroup_name.setter # type: ignore
    def nodegroup_name(self, value: typing.Optional[builtins.str]) -> None:
        jsii.set(self, "nodegroupName", value)

    @builtins.property # type: ignore
    @jsii.member(jsii_name="releaseVersion")
    def release_version(self) -> typing.Optional[builtins.str]:
        """``AWS::EKS::Nodegroup.ReleaseVersion``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-releaseversion
        """
        return jsii.get(self, "releaseVersion")

    @release_version.setter # type: ignore
    def release_version(self, value: typing.Optional[builtins.str]) -> None:
        jsii.set(self, "releaseVersion", value)

    @builtins.property # type: ignore
    @jsii.member(jsii_name="remoteAccess")
    def remote_access(
        self,
    ) -> typing.Optional[typing.Union[aws_cdk.core.IResolvable, "CfnNodegroup.RemoteAccessProperty"]]:
        """``AWS::EKS::Nodegroup.RemoteAccess``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-remoteaccess
        """
        return jsii.get(self, "remoteAccess")

    @remote_access.setter # type: ignore
    def remote_access(
        self,
        value: typing.Optional[typing.Union[aws_cdk.core.IResolvable, "CfnNodegroup.RemoteAccessProperty"]],
    ) -> None:
        jsii.set(self, "remoteAccess", value)

    @builtins.property # type: ignore
    @jsii.member(jsii_name="scalingConfig")
    def scaling_config(
        self,
    ) -> typing.Optional[typing.Union[aws_cdk.core.IResolvable, "CfnNodegroup.ScalingConfigProperty"]]:
        """``AWS::EKS::Nodegroup.ScalingConfig``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-scalingconfig
        """
        return jsii.get(self, "scalingConfig")

    @scaling_config.setter # type: ignore
    def scaling_config(
        self,
        value: typing.Optional[typing.Union[aws_cdk.core.IResolvable, "CfnNodegroup.ScalingConfigProperty"]],
    ) -> None:
        jsii.set(self, "scalingConfig", value)

    @builtins.property # type: ignore
    @jsii.member(jsii_name="version")
    def version(self) -> typing.Optional[builtins.str]:
        """``AWS::EKS::Nodegroup.Version``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-version
        """
        return jsii.get(self, "version")

    @version.setter # type: ignore
    def version(self, value: typing.Optional[builtins.str]) -> None:
        jsii.set(self, "version", value)

    @jsii.data_type(
        jsii_type="@aws-cdk/aws-eks.CfnNodegroup.LaunchTemplateSpecificationProperty",
        jsii_struct_bases=[],
        name_mapping={"id": "id", "name": "name", "version": "version"},
    )
    class LaunchTemplateSpecificationProperty:
        def __init__(
            self,
            *,
            id: typing.Optional[builtins.str] = None,
            name: typing.Optional[builtins.str] = None,
            version: typing.Optional[builtins.str] = None,
        ) -> None:
            """
            :param id: ``CfnNodegroup.LaunchTemplateSpecificationProperty.Id``.
            :param name: ``CfnNodegroup.LaunchTemplateSpecificationProperty.Name``.
            :param version: ``CfnNodegroup.LaunchTemplateSpecificationProperty.Version``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-nodegroup-launchtemplatespecification.html
            """
            self._values: typing.Dict[str, typing.Any] = {}
            if id is not None:
                self._values["id"] = id
            if name is not None:
                self._values["name"] = name
            if version is not None:
                self._values["version"] = version

        @builtins.property
        def id(self) -> typing.Optional[builtins.str]:
            """``CfnNodegroup.LaunchTemplateSpecificationProperty.Id``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-nodegroup-launchtemplatespecification.html#cfn-eks-nodegroup-launchtemplatespecification-id
            """
            result = self._values.get("id")
            return result

        @builtins.property
        def name(self) -> typing.Optional[builtins.str]:
            """``CfnNodegroup.LaunchTemplateSpecificationProperty.Name``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-nodegroup-launchtemplatespecification.html#cfn-eks-nodegroup-launchtemplatespecification-name
            """
            result = self._values.get("name")
            return result

        @builtins.property
        def version(self) -> typing.Optional[builtins.str]:
            """``CfnNodegroup.LaunchTemplateSpecificationProperty.Version``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-nodegroup-launchtemplatespecification.html#cfn-eks-nodegroup-launchtemplatespecification-version
            """
            result = self._values.get("version")
            return result

        def __eq__(self, rhs: typing.Any) -> builtins.bool:
            return isinstance(rhs, self.__class__) and rhs._values == self._values

        def __ne__(self, rhs: typing.Any) -> builtins.bool:
            return not (rhs == self)

        def __repr__(self) -> str:
            return "LaunchTemplateSpecificationProperty(%s)" % ", ".join(
                k + "=" + repr(v) for k, v in self._values.items()
            )

    @jsii.data_type(
        jsii_type="@aws-cdk/aws-eks.CfnNodegroup.RemoteAccessProperty",
        jsii_struct_bases=[],
        name_mapping={
            "ec2_ssh_key": "ec2SshKey",
            "source_security_groups": "sourceSecurityGroups",
        },
    )
    class RemoteAccessProperty:
        def __init__(
            self,
            *,
            ec2_ssh_key: builtins.str,
            source_security_groups: typing.Optional[typing.List[builtins.str]] = None,
        ) -> None:
            """
            :param ec2_ssh_key: ``CfnNodegroup.RemoteAccessProperty.Ec2SshKey``.
            :param source_security_groups: ``CfnNodegroup.RemoteAccessProperty.SourceSecurityGroups``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-nodegroup-remoteaccess.html
            """
            self._values: typing.Dict[str, typing.Any] = {
                "ec2_ssh_key": ec2_ssh_key,
            }
            if source_security_groups is not None:
                self._values["source_security_groups"] = source_security_groups

        @builtins.property
        def ec2_ssh_key(self) -> builtins.str:
            """``CfnNodegroup.RemoteAccessProperty.Ec2SshKey``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-nodegroup-remoteaccess.html#cfn-eks-nodegroup-remoteaccess-ec2sshkey
            """
            result = self._values.get("ec2_ssh_key")
            assert result is not None, "Required property 'ec2_ssh_key' is missing"
            return result

        @builtins.property
        def source_security_groups(self) -> typing.Optional[typing.List[builtins.str]]:
            """``CfnNodegroup.RemoteAccessProperty.SourceSecurityGroups``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-nodegroup-remoteaccess.html#cfn-eks-nodegroup-remoteaccess-sourcesecuritygroups
            """
            result = self._values.get("source_security_groups")
            return result

        def __eq__(self, rhs: typing.Any) -> builtins.bool:
            return isinstance(rhs, self.__class__) and rhs._values == self._values

        def __ne__(self, rhs: typing.Any) -> builtins.bool:
            return not (rhs == self)

        def __repr__(self) -> str:
            return "RemoteAccessProperty(%s)" % ", ".join(
                k + "=" + repr(v) for k, v in self._values.items()
            )

    @jsii.data_type(
        jsii_type="@aws-cdk/aws-eks.CfnNodegroup.ScalingConfigProperty",
        jsii_struct_bases=[],
        name_mapping={
            "desired_size": "desiredSize",
            "max_size": "maxSize",
            "min_size": "minSize",
        },
    )
    class ScalingConfigProperty:
        def __init__(
            self,
            *,
            desired_size: typing.Optional[jsii.Number] = None,
            max_size: typing.Optional[jsii.Number] = None,
            min_size: typing.Optional[jsii.Number] = None,
        ) -> None:
            """
            :param desired_size: ``CfnNodegroup.ScalingConfigProperty.DesiredSize``.
            :param max_size: ``CfnNodegroup.ScalingConfigProperty.MaxSize``.
            :param min_size: ``CfnNodegroup.ScalingConfigProperty.MinSize``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-nodegroup-scalingconfig.html
            """
            self._values: typing.Dict[str, typing.Any] = {}
            if desired_size is not None:
                self._values["desired_size"] = desired_size
            if max_size is not None:
                self._values["max_size"] = max_size
            if min_size is not None:
                self._values["min_size"] = min_size

        @builtins.property
        def desired_size(self) -> typing.Optional[jsii.Number]:
            """``CfnNodegroup.ScalingConfigProperty.DesiredSize``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-nodegroup-scalingconfig.html#cfn-eks-nodegroup-scalingconfig-desiredsize
            """
            result = self._values.get("desired_size")
            return result

        @builtins.property
        def max_size(self) -> typing.Optional[jsii.Number]:
            """``CfnNodegroup.ScalingConfigProperty.MaxSize``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-nodegroup-scalingconfig.html#cfn-eks-nodegroup-scalingconfig-maxsize
            """
            result = self._values.get("max_size")
            return result

        @builtins.property
        def min_size(self) -> typing.Optional[jsii.Number]:
            """``CfnNodegroup.ScalingConfigProperty.MinSize``.

            :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-nodegroup-scalingconfig.html#cfn-eks-nodegroup-scalingconfig-minsize
            """
            result = self._values.get("min_size")
            return result

        def __eq__(self, rhs: typing.Any) -> builtins.bool:
            return isinstance(rhs, self.__class__) and rhs._values == self._values

        def __ne__(self, rhs: typing.Any) -> builtins.bool:
            return not (rhs == self)

        def __repr__(self) -> str:
            return "ScalingConfigProperty(%s)" % ", ".join(
                k + "=" + repr(v) for k, v in self._values.items()
            )


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.CfnNodegroupProps",
    jsii_struct_bases=[],
    name_mapping={
        "cluster_name": "clusterName",
        "node_role": "nodeRole",
        "subnets": "subnets",
        "ami_type": "amiType",
        "disk_size": "diskSize",
        "force_update_enabled": "forceUpdateEnabled",
        "instance_types": "instanceTypes",
        "labels": "labels",
        "launch_template": "launchTemplate",
        "nodegroup_name": "nodegroupName",
        "release_version": "releaseVersion",
        "remote_access": "remoteAccess",
        "scaling_config": "scalingConfig",
        "tags": "tags",
        "version": "version",
    },
)
class CfnNodegroupProps:
    def __init__(
        self,
        *,
        cluster_name: builtins.str,
        node_role: builtins.str,
        subnets: typing.List[builtins.str],
        ami_type: typing.Optional[builtins.str] = None,
        disk_size: typing.Optional[jsii.Number] = None,
        force_update_enabled: typing.Optional[typing.Union[builtins.bool, aws_cdk.core.IResolvable]] = None,
        instance_types: typing.Optional[typing.List[builtins.str]] = None,
        labels: typing.Any = None,
        launch_template: typing.Optional[typing.Union[aws_cdk.core.IResolvable, CfnNodegroup.LaunchTemplateSpecificationProperty]] = None,
        nodegroup_name: typing.Optional[builtins.str] = None,
        release_version: typing.Optional[builtins.str] = None,
        remote_access: typing.Optional[typing.Union[aws_cdk.core.IResolvable, CfnNodegroup.RemoteAccessProperty]] = None,
        scaling_config: typing.Optional[typing.Union[aws_cdk.core.IResolvable, CfnNodegroup.ScalingConfigProperty]] = None,
        tags: typing.Any = None,
        version: typing.Optional[builtins.str] = None,
    ) -> None:
        """Properties for defining a ``AWS::EKS::Nodegroup``.

        :param cluster_name: ``AWS::EKS::Nodegroup.ClusterName``.
        :param node_role: ``AWS::EKS::Nodegroup.NodeRole``.
        :param subnets: ``AWS::EKS::Nodegroup.Subnets``.
        :param ami_type: ``AWS::EKS::Nodegroup.AmiType``.
        :param disk_size: ``AWS::EKS::Nodegroup.DiskSize``.
        :param force_update_enabled: ``AWS::EKS::Nodegroup.ForceUpdateEnabled``.
        :param instance_types: ``AWS::EKS::Nodegroup.InstanceTypes``.
        :param labels: ``AWS::EKS::Nodegroup.Labels``.
        :param launch_template: ``AWS::EKS::Nodegroup.LaunchTemplate``.
        :param nodegroup_name: ``AWS::EKS::Nodegroup.NodegroupName``.
        :param release_version: ``AWS::EKS::Nodegroup.ReleaseVersion``.
        :param remote_access: ``AWS::EKS::Nodegroup.RemoteAccess``.
        :param scaling_config: ``AWS::EKS::Nodegroup.ScalingConfig``.
        :param tags: ``AWS::EKS::Nodegroup.Tags``.
        :param version: ``AWS::EKS::Nodegroup.Version``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html
        """
        self._values: typing.Dict[str, typing.Any] = {
            "cluster_name": cluster_name,
            "node_role": node_role,
            "subnets": subnets,
        }
        if ami_type is not None:
            self._values["ami_type"] = ami_type
        if disk_size is not None:
            self._values["disk_size"] = disk_size
        if force_update_enabled is not None:
            self._values["force_update_enabled"] = force_update_enabled
        if instance_types is not None:
            self._values["instance_types"] = instance_types
        if labels is not None:
            self._values["labels"] = labels
        if launch_template is not None:
            self._values["launch_template"] = launch_template
        if nodegroup_name is not None:
            self._values["nodegroup_name"] = nodegroup_name
        if release_version is not None:
            self._values["release_version"] = release_version
        if remote_access is not None:
            self._values["remote_access"] = remote_access
        if scaling_config is not None:
            self._values["scaling_config"] = scaling_config
        if tags is not None:
            self._values["tags"] = tags
        if version is not None:
            self._values["version"] = version

    @builtins.property
    def cluster_name(self) -> builtins.str:
        """``AWS::EKS::Nodegroup.ClusterName``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-clustername
        """
        result = self._values.get("cluster_name")
        assert result is not None, "Required property 'cluster_name' is missing"
        return result

    @builtins.property
    def node_role(self) -> builtins.str:
        """``AWS::EKS::Nodegroup.NodeRole``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-noderole
        """
        result = self._values.get("node_role")
        assert result is not None, "Required property 'node_role' is missing"
        return result

    @builtins.property
    def subnets(self) -> typing.List[builtins.str]:
        """``AWS::EKS::Nodegroup.Subnets``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-subnets
        """
        result = self._values.get("subnets")
        assert result is not None, "Required property 'subnets' is missing"
        return result

    @builtins.property
    def ami_type(self) -> typing.Optional[builtins.str]:
        """``AWS::EKS::Nodegroup.AmiType``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-amitype
        """
        result = self._values.get("ami_type")
        return result

    @builtins.property
    def disk_size(self) -> typing.Optional[jsii.Number]:
        """``AWS::EKS::Nodegroup.DiskSize``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-disksize
        """
        result = self._values.get("disk_size")
        return result

    @builtins.property
    def force_update_enabled(
        self,
    ) -> typing.Optional[typing.Union[builtins.bool, aws_cdk.core.IResolvable]]:
        """``AWS::EKS::Nodegroup.ForceUpdateEnabled``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-forceupdateenabled
        """
        result = self._values.get("force_update_enabled")
        return result

    @builtins.property
    def instance_types(self) -> typing.Optional[typing.List[builtins.str]]:
        """``AWS::EKS::Nodegroup.InstanceTypes``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-instancetypes
        """
        result = self._values.get("instance_types")
        return result

    @builtins.property
    def labels(self) -> typing.Any:
        """``AWS::EKS::Nodegroup.Labels``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-labels
        """
        result = self._values.get("labels")
        return result

    @builtins.property
    def launch_template(
        self,
    ) -> typing.Optional[typing.Union[aws_cdk.core.IResolvable, CfnNodegroup.LaunchTemplateSpecificationProperty]]:
        """``AWS::EKS::Nodegroup.LaunchTemplate``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-launchtemplate
        """
        result = self._values.get("launch_template")
        return result

    @builtins.property
    def nodegroup_name(self) -> typing.Optional[builtins.str]:
        """``AWS::EKS::Nodegroup.NodegroupName``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-nodegroupname
        """
        result = self._values.get("nodegroup_name")
        return result

    @builtins.property
    def release_version(self) -> typing.Optional[builtins.str]:
        """``AWS::EKS::Nodegroup.ReleaseVersion``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-releaseversion
        """
        result = self._values.get("release_version")
        return result

    @builtins.property
    def remote_access(
        self,
    ) -> typing.Optional[typing.Union[aws_cdk.core.IResolvable, CfnNodegroup.RemoteAccessProperty]]:
        """``AWS::EKS::Nodegroup.RemoteAccess``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-remoteaccess
        """
        result = self._values.get("remote_access")
        return result

    @builtins.property
    def scaling_config(
        self,
    ) -> typing.Optional[typing.Union[aws_cdk.core.IResolvable, CfnNodegroup.ScalingConfigProperty]]:
        """``AWS::EKS::Nodegroup.ScalingConfig``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-scalingconfig
        """
        result = self._values.get("scaling_config")
        return result

    @builtins.property
    def tags(self) -> typing.Any:
        """``AWS::EKS::Nodegroup.Tags``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-tags
        """
        result = self._values.get("tags")
        return result

    @builtins.property
    def version(self) -> typing.Optional[builtins.str]:
        """``AWS::EKS::Nodegroup.Version``.

        :see: http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-eks-nodegroup.html#cfn-eks-nodegroup-version
        """
        result = self._values.get("version")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "CfnNodegroupProps(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.ClusterAttributes",
    jsii_struct_bases=[],
    name_mapping={
        "cluster_name": "clusterName",
        "cluster_certificate_authority_data": "clusterCertificateAuthorityData",
        "cluster_encryption_config_key_arn": "clusterEncryptionConfigKeyArn",
        "cluster_endpoint": "clusterEndpoint",
        "cluster_security_group_id": "clusterSecurityGroupId",
        "kubectl_environment": "kubectlEnvironment",
        "kubectl_layer": "kubectlLayer",
        "kubectl_memory": "kubectlMemory",
        "kubectl_private_subnet_ids": "kubectlPrivateSubnetIds",
        "kubectl_role_arn": "kubectlRoleArn",
        "kubectl_security_group_id": "kubectlSecurityGroupId",
        "open_id_connect_provider": "openIdConnectProvider",
        "prune": "prune",
        "security_group_ids": "securityGroupIds",
        "vpc": "vpc",
    },
)
class ClusterAttributes:
    def __init__(
        self,
        *,
        cluster_name: builtins.str,
        cluster_certificate_authority_data: typing.Optional[builtins.str] = None,
        cluster_encryption_config_key_arn: typing.Optional[builtins.str] = None,
        cluster_endpoint: typing.Optional[builtins.str] = None,
        cluster_security_group_id: typing.Optional[builtins.str] = None,
        kubectl_environment: typing.Optional[typing.Mapping[builtins.str, builtins.str]] = None,
        kubectl_layer: typing.Optional[aws_cdk.aws_lambda.ILayerVersion] = None,
        kubectl_memory: typing.Optional[aws_cdk.core.Size] = None,
        kubectl_private_subnet_ids: typing.Optional[typing.List[builtins.str]] = None,
        kubectl_role_arn: typing.Optional[builtins.str] = None,
        kubectl_security_group_id: typing.Optional[builtins.str] = None,
        open_id_connect_provider: typing.Optional[aws_cdk.aws_iam.IOpenIdConnectProvider] = None,
        prune: typing.Optional[builtins.bool] = None,
        security_group_ids: typing.Optional[typing.List[builtins.str]] = None,
        vpc: typing.Optional[aws_cdk.aws_ec2.IVpc] = None,
    ) -> None:
        """(experimental) Attributes for EKS clusters.

        :param cluster_name: (experimental) The physical name of the Cluster.
        :param cluster_certificate_authority_data: (experimental) The certificate-authority-data for your cluster. Default: - if not specified ``cluster.clusterCertificateAuthorityData`` will throw an error
        :param cluster_encryption_config_key_arn: (experimental) Amazon Resource Name (ARN) or alias of the customer master key (CMK). Default: - if not specified ``cluster.clusterEncryptionConfigKeyArn`` will throw an error
        :param cluster_endpoint: (experimental) The API Server endpoint URL. Default: - if not specified ``cluster.clusterEndpoint`` will throw an error.
        :param cluster_security_group_id: (experimental) The cluster security group that was created by Amazon EKS for the cluster. Default: - if not specified ``cluster.clusterSecurityGroupId`` will throw an error
        :param kubectl_environment: (experimental) Environment variables to use when running ``kubectl`` against this cluster. Default: - no additional variables
        :param kubectl_layer: (experimental) An AWS Lambda Layer which includes ``kubectl``, Helm and the AWS CLI. By default, the provider will use the layer included in the "aws-lambda-layer-kubectl" SAR application which is available in all commercial regions. To deploy the layer locally, visit https://github.com/aws-samples/aws-lambda-layer-kubectl/blob/master/cdk/README.md for instructions on how to prepare the .zip file and then define it in your app as follows:: const layer = new lambda.LayerVersion(this, 'kubectl-layer', { code: lambda.Code.fromAsset(`${__dirname}/layer.zip`)), compatibleRuntimes: [lambda.Runtime.PROVIDED] }); Or you can use the standard layer like this (with options to customize the version and SAR application ID): ```ts const layer = new eks.KubectlLayer(this, 'KubectlLayer'); Default: - the layer provided by the ``aws-lambda-layer-kubectl`` SAR app.
        :param kubectl_memory: (experimental) Amount of memory to allocate to the provider's lambda function. Default: Size.gibibytes(1)
        :param kubectl_private_subnet_ids: (experimental) Subnets to host the ``kubectl`` compute resources. If not specified, the k8s endpoint is expected to be accessible publicly. Default: - k8s endpoint is expected to be accessible publicly
        :param kubectl_role_arn: (experimental) An IAM role with cluster administrator and "system:masters" permissions. Default: - if not specified, it not be possible to issue ``kubectl`` commands against an imported cluster.
        :param kubectl_security_group_id: (experimental) A security group to use for ``kubectl`` execution. If not specified, the k8s endpoint is expected to be accessible publicly. Default: - k8s endpoint is expected to be accessible publicly
        :param open_id_connect_provider: (experimental) An Open ID Connect provider for this cluster that can be used to configure service accounts. You can either import an existing provider using ``iam.OpenIdConnectProvider.fromProviderArn``, or create a new provider using ``new eks.OpenIdConnectProvider`` Default: - if not specified ``cluster.openIdConnectProvider`` and ``cluster.addServiceAccount`` will throw an error.
        :param prune: (experimental) Indicates whether Kubernetes resources added through ``addManifest()`` can be automatically pruned. When this is enabled (default), prune labels will be allocated and injected to each resource. These labels will then be used when issuing the ``kubectl apply`` operation with the ``--prune`` switch. Default: true
        :param security_group_ids: (experimental) Additional security groups associated with this cluster. Default: - if not specified, no additional security groups will be considered in ``cluster.connections``.
        :param vpc: (experimental) The VPC in which this Cluster was created. Default: - if not specified ``cluster.vpc`` will throw an error

        :stability: experimental
        """
        self._values: typing.Dict[str, typing.Any] = {
            "cluster_name": cluster_name,
        }
        if cluster_certificate_authority_data is not None:
            self._values["cluster_certificate_authority_data"] = cluster_certificate_authority_data
        if cluster_encryption_config_key_arn is not None:
            self._values["cluster_encryption_config_key_arn"] = cluster_encryption_config_key_arn
        if cluster_endpoint is not None:
            self._values["cluster_endpoint"] = cluster_endpoint
        if cluster_security_group_id is not None:
            self._values["cluster_security_group_id"] = cluster_security_group_id
        if kubectl_environment is not None:
            self._values["kubectl_environment"] = kubectl_environment
        if kubectl_layer is not None:
            self._values["kubectl_layer"] = kubectl_layer
        if kubectl_memory is not None:
            self._values["kubectl_memory"] = kubectl_memory
        if kubectl_private_subnet_ids is not None:
            self._values["kubectl_private_subnet_ids"] = kubectl_private_subnet_ids
        if kubectl_role_arn is not None:
            self._values["kubectl_role_arn"] = kubectl_role_arn
        if kubectl_security_group_id is not None:
            self._values["kubectl_security_group_id"] = kubectl_security_group_id
        if open_id_connect_provider is not None:
            self._values["open_id_connect_provider"] = open_id_connect_provider
        if prune is not None:
            self._values["prune"] = prune
        if security_group_ids is not None:
            self._values["security_group_ids"] = security_group_ids
        if vpc is not None:
            self._values["vpc"] = vpc

    @builtins.property
    def cluster_name(self) -> builtins.str:
        """(experimental) The physical name of the Cluster.

        :stability: experimental
        """
        result = self._values.get("cluster_name")
        assert result is not None, "Required property 'cluster_name' is missing"
        return result

    @builtins.property
    def cluster_certificate_authority_data(self) -> typing.Optional[builtins.str]:
        """(experimental) The certificate-authority-data for your cluster.

        :default:

        - if not specified ``cluster.clusterCertificateAuthorityData`` will
        throw an error

        :stability: experimental
        """
        result = self._values.get("cluster_certificate_authority_data")
        return result

    @builtins.property
    def cluster_encryption_config_key_arn(self) -> typing.Optional[builtins.str]:
        """(experimental) Amazon Resource Name (ARN) or alias of the customer master key (CMK).

        :default:

        - if not specified ``cluster.clusterEncryptionConfigKeyArn`` will
        throw an error

        :stability: experimental
        """
        result = self._values.get("cluster_encryption_config_key_arn")
        return result

    @builtins.property
    def cluster_endpoint(self) -> typing.Optional[builtins.str]:
        """(experimental) The API Server endpoint URL.

        :default: - if not specified ``cluster.clusterEndpoint`` will throw an error.

        :stability: experimental
        """
        result = self._values.get("cluster_endpoint")
        return result

    @builtins.property
    def cluster_security_group_id(self) -> typing.Optional[builtins.str]:
        """(experimental) The cluster security group that was created by Amazon EKS for the cluster.

        :default:

        - if not specified ``cluster.clusterSecurityGroupId`` will throw an
        error

        :stability: experimental
        """
        result = self._values.get("cluster_security_group_id")
        return result

    @builtins.property
    def kubectl_environment(
        self,
    ) -> typing.Optional[typing.Mapping[builtins.str, builtins.str]]:
        """(experimental) Environment variables to use when running ``kubectl`` against this cluster.

        :default: - no additional variables

        :stability: experimental
        """
        result = self._values.get("kubectl_environment")
        return result

    @builtins.property
    def kubectl_layer(self) -> typing.Optional[aws_cdk.aws_lambda.ILayerVersion]:
        """(experimental) An AWS Lambda Layer which includes ``kubectl``, Helm and the AWS CLI.

        By default, the provider will use the layer included in the
        "aws-lambda-layer-kubectl" SAR application which is available in all
        commercial regions.

        To deploy the layer locally, visit
        https://github.com/aws-samples/aws-lambda-layer-kubectl/blob/master/cdk/README.md
        for instructions on how to prepare the .zip file and then define it in your
        app as follows::

           # Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
           layer = lambda_.LayerVersion(self, "kubectl-layer",
               code=lambda_.Code.from_asset(f"{__dirname}/layer.zip")
           )
           compatible_runtimes =

           Oryoucanusethestandardlayerlikeself()with options
           tocustomizetheversionandSARapplicationID

           ```ts
           const layer = new eks.KubectlLayer(this, 'KubectlLayer');

        :default: - the layer provided by the ``aws-lambda-layer-kubectl`` SAR app.

        :see: https://github.com/aws-samples/aws-lambda-layer-kubectl
        :stability: experimental
        """
        result = self._values.get("kubectl_layer")
        return result

    @builtins.property
    def kubectl_memory(self) -> typing.Optional[aws_cdk.core.Size]:
        """(experimental) Amount of memory to allocate to the provider's lambda function.

        :default: Size.gibibytes(1)

        :stability: experimental
        """
        result = self._values.get("kubectl_memory")
        return result

    @builtins.property
    def kubectl_private_subnet_ids(self) -> typing.Optional[typing.List[builtins.str]]:
        """(experimental) Subnets to host the ``kubectl`` compute resources.

        If not specified, the k8s
        endpoint is expected to be accessible publicly.

        :default: - k8s endpoint is expected to be accessible publicly

        :stability: experimental
        """
        result = self._values.get("kubectl_private_subnet_ids")
        return result

    @builtins.property
    def kubectl_role_arn(self) -> typing.Optional[builtins.str]:
        """(experimental) An IAM role with cluster administrator and "system:masters" permissions.

        :default:

        - if not specified, it not be possible to issue ``kubectl`` commands
        against an imported cluster.

        :stability: experimental
        """
        result = self._values.get("kubectl_role_arn")
        return result

    @builtins.property
    def kubectl_security_group_id(self) -> typing.Optional[builtins.str]:
        """(experimental) A security group to use for ``kubectl`` execution.

        If not specified, the k8s
        endpoint is expected to be accessible publicly.

        :default: - k8s endpoint is expected to be accessible publicly

        :stability: experimental
        """
        result = self._values.get("kubectl_security_group_id")
        return result

    @builtins.property
    def open_id_connect_provider(
        self,
    ) -> typing.Optional[aws_cdk.aws_iam.IOpenIdConnectProvider]:
        """(experimental) An Open ID Connect provider for this cluster that can be used to configure service accounts.

        You can either import an existing provider using ``iam.OpenIdConnectProvider.fromProviderArn``,
        or create a new provider using ``new eks.OpenIdConnectProvider``

        :default: - if not specified ``cluster.openIdConnectProvider`` and ``cluster.addServiceAccount`` will throw an error.

        :stability: experimental
        """
        result = self._values.get("open_id_connect_provider")
        return result

    @builtins.property
    def prune(self) -> typing.Optional[builtins.bool]:
        """(experimental) Indicates whether Kubernetes resources added through ``addManifest()`` can be automatically pruned.

        When this is enabled (default), prune labels will be
        allocated and injected to each resource. These labels will then be used
        when issuing the ``kubectl apply`` operation with the ``--prune`` switch.

        :default: true

        :stability: experimental
        """
        result = self._values.get("prune")
        return result

    @builtins.property
    def security_group_ids(self) -> typing.Optional[typing.List[builtins.str]]:
        """(experimental) Additional security groups associated with this cluster.

        :default:

        - if not specified, no additional security groups will be
        considered in ``cluster.connections``.

        :stability: experimental
        """
        result = self._values.get("security_group_ids")
        return result

    @builtins.property
    def vpc(self) -> typing.Optional[aws_cdk.aws_ec2.IVpc]:
        """(experimental) The VPC in which this Cluster was created.

        :default: - if not specified ``cluster.vpc`` will throw an error

        :stability: experimental
        """
        result = self._values.get("vpc")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "ClusterAttributes(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.CommonClusterOptions",
    jsii_struct_bases=[],
    name_mapping={
        "version": "version",
        "cluster_name": "clusterName",
        "output_cluster_name": "outputClusterName",
        "output_config_command": "outputConfigCommand",
        "role": "role",
        "security_group": "securityGroup",
        "vpc": "vpc",
        "vpc_subnets": "vpcSubnets",
    },
)
class CommonClusterOptions:
    def __init__(
        self,
        *,
        version: "KubernetesVersion",
        cluster_name: typing.Optional[builtins.str] = None,
        output_cluster_name: typing.Optional[builtins.bool] = None,
        output_config_command: typing.Optional[builtins.bool] = None,
        role: typing.Optional[aws_cdk.aws_iam.IRole] = None,
        security_group: typing.Optional[aws_cdk.aws_ec2.ISecurityGroup] = None,
        vpc: typing.Optional[aws_cdk.aws_ec2.IVpc] = None,
        vpc_subnets: typing.Optional[typing.List[aws_cdk.aws_ec2.SubnetSelection]] = None,
    ) -> None:
        """(experimental) Options for configuring an EKS cluster.

        :param version: (experimental) The Kubernetes version to run in the cluster.
        :param cluster_name: (experimental) Name for the cluster. Default: - Automatically generated name
        :param output_cluster_name: (experimental) Determines whether a CloudFormation output with the name of the cluster will be synthesized. Default: false
        :param output_config_command: (experimental) Determines whether a CloudFormation output with the ``aws eks update-kubeconfig`` command will be synthesized. This command will include the cluster name and, if applicable, the ARN of the masters IAM role. Default: true
        :param role: (experimental) Role that provides permissions for the Kubernetes control plane to make calls to AWS API operations on your behalf. Default: - A role is automatically created for you
        :param security_group: (experimental) Security Group to use for Control Plane ENIs. Default: - A security group is automatically created
        :param vpc: (experimental) The VPC in which to create the Cluster. Default: - a VPC with default configuration will be created and can be accessed through ``cluster.vpc``.
        :param vpc_subnets: (experimental) Where to place EKS Control Plane ENIs. If you want to create public load balancers, this must include public subnets. For example, to only select private subnets, supply the following:: vpcSubnets: [ { subnetType: ec2.SubnetType.Private } ] Default: - All public and private subnets

        :stability: experimental
        """
        self._values: typing.Dict[str, typing.Any] = {
            "version": version,
        }
        if cluster_name is not None:
            self._values["cluster_name"] = cluster_name
        if output_cluster_name is not None:
            self._values["output_cluster_name"] = output_cluster_name
        if output_config_command is not None:
            self._values["output_config_command"] = output_config_command
        if role is not None:
            self._values["role"] = role
        if security_group is not None:
            self._values["security_group"] = security_group
        if vpc is not None:
            self._values["vpc"] = vpc
        if vpc_subnets is not None:
            self._values["vpc_subnets"] = vpc_subnets

    @builtins.property
    def version(self) -> "KubernetesVersion":
        """(experimental) The Kubernetes version to run in the cluster.

        :stability: experimental
        """
        result = self._values.get("version")
        assert result is not None, "Required property 'version' is missing"
        return result

    @builtins.property
    def cluster_name(self) -> typing.Optional[builtins.str]:
        """(experimental) Name for the cluster.

        :default: - Automatically generated name

        :stability: experimental
        """
        result = self._values.get("cluster_name")
        return result

    @builtins.property
    def output_cluster_name(self) -> typing.Optional[builtins.bool]:
        """(experimental) Determines whether a CloudFormation output with the name of the cluster will be synthesized.

        :default: false

        :stability: experimental
        """
        result = self._values.get("output_cluster_name")
        return result

    @builtins.property
    def output_config_command(self) -> typing.Optional[builtins.bool]:
        """(experimental) Determines whether a CloudFormation output with the ``aws eks update-kubeconfig`` command will be synthesized.

        This command will include
        the cluster name and, if applicable, the ARN of the masters IAM role.

        :default: true

        :stability: experimental
        """
        result = self._values.get("output_config_command")
        return result

    @builtins.property
    def role(self) -> typing.Optional[aws_cdk.aws_iam.IRole]:
        """(experimental) Role that provides permissions for the Kubernetes control plane to make calls to AWS API operations on your behalf.

        :default: - A role is automatically created for you

        :stability: experimental
        """
        result = self._values.get("role")
        return result

    @builtins.property
    def security_group(self) -> typing.Optional[aws_cdk.aws_ec2.ISecurityGroup]:
        """(experimental) Security Group to use for Control Plane ENIs.

        :default: - A security group is automatically created

        :stability: experimental
        """
        result = self._values.get("security_group")
        return result

    @builtins.property
    def vpc(self) -> typing.Optional[aws_cdk.aws_ec2.IVpc]:
        """(experimental) The VPC in which to create the Cluster.

        :default: - a VPC with default configuration will be created and can be accessed through ``cluster.vpc``.

        :stability: experimental
        """
        result = self._values.get("vpc")
        return result

    @builtins.property
    def vpc_subnets(
        self,
    ) -> typing.Optional[typing.List[aws_cdk.aws_ec2.SubnetSelection]]:
        """(experimental) Where to place EKS Control Plane ENIs.

        If you want to create public load balancers, this must include public subnets.

        For example, to only select private subnets, supply the following::

           # Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
           vpcSubnets: [
              { subnetType: ec2.SubnetType.Private }
           ]

        :default: - All public and private subnets

        :stability: experimental
        """
        result = self._values.get("vpc_subnets")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "CommonClusterOptions(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


@jsii.enum(jsii_type="@aws-cdk/aws-eks.CoreDnsComputeType")
class CoreDnsComputeType(enum.Enum):
    """(experimental) The type of compute resources to use for CoreDNS.

    :stability: experimental
    """

    EC2 = "EC2"
    """(experimental) Deploy CoreDNS on EC2 instances.

    :stability: experimental
    """
    FARGATE = "FARGATE"
    """(experimental) Deploy CoreDNS on Fargate-managed instances.

    :stability: experimental
    """


@jsii.enum(jsii_type="@aws-cdk/aws-eks.CpuArch")
class CpuArch(enum.Enum):
    """(experimental) CPU architecture.

    :stability: experimental
    """

    ARM_64 = "ARM_64"
    """(experimental) arm64 CPU type.

    :stability: experimental
    """
    X86_64 = "X86_64"
    """(experimental) x86_64 CPU type.

    :stability: experimental
    """


@jsii.enum(jsii_type="@aws-cdk/aws-eks.DefaultCapacityType")
class DefaultCapacityType(enum.Enum):
    """(experimental) The default capacity type for the cluster.

    :stability: experimental
    """

    NODEGROUP = "NODEGROUP"
    """(experimental) managed node group.

    :stability: experimental
    """
    EC2 = "EC2"
    """(experimental) EC2 autoscaling group.

    :stability: experimental
    """


@jsii.implements(aws_cdk.aws_ec2.IMachineImage)
class EksOptimizedImage(
    metaclass=jsii.JSIIMeta,
    jsii_type="@aws-cdk/aws-eks.EksOptimizedImage",
):
    """(experimental) Construct an Amazon Linux 2 image from the latest EKS Optimized AMI published in SSM.

    :stability: experimental
    """

    def __init__(
        self,
        *,
        cpu_arch: typing.Optional[CpuArch] = None,
        kubernetes_version: typing.Optional[builtins.str] = None,
        node_type: typing.Optional["NodeType"] = None,
    ) -> None:
        """(experimental) Constructs a new instance of the EcsOptimizedAmi class.

        :param cpu_arch: (experimental) What cpu architecture to retrieve the image for (arm64 or x86_64). Default: CpuArch.X86_64
        :param kubernetes_version: (experimental) The Kubernetes version to use. Default: - The latest version
        :param node_type: (experimental) What instance type to retrieve the image for (standard or GPU-optimized). Default: NodeType.STANDARD

        :stability: experimental
        """
        props = EksOptimizedImageProps(
            cpu_arch=cpu_arch,
            kubernetes_version=kubernetes_version,
            node_type=node_type,
        )

        jsii.create(EksOptimizedImage, self, [props])

    @jsii.member(jsii_name="getImage")
    def get_image(
        self,
        scope: aws_cdk.core.Construct,
    ) -> aws_cdk.aws_ec2.MachineImageConfig:
        """(experimental) Return the correct image.

        :param scope: -

        :stability: experimental
        """
        return jsii.invoke(self, "getImage", [scope])


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.EksOptimizedImageProps",
    jsii_struct_bases=[],
    name_mapping={
        "cpu_arch": "cpuArch",
        "kubernetes_version": "kubernetesVersion",
        "node_type": "nodeType",
    },
)
class EksOptimizedImageProps:
    def __init__(
        self,
        *,
        cpu_arch: typing.Optional[CpuArch] = None,
        kubernetes_version: typing.Optional[builtins.str] = None,
        node_type: typing.Optional["NodeType"] = None,
    ) -> None:
        """(experimental) Properties for EksOptimizedImage.

        :param cpu_arch: (experimental) What cpu architecture to retrieve the image for (arm64 or x86_64). Default: CpuArch.X86_64
        :param kubernetes_version: (experimental) The Kubernetes version to use. Default: - The latest version
        :param node_type: (experimental) What instance type to retrieve the image for (standard or GPU-optimized). Default: NodeType.STANDARD

        :stability: experimental
        """
        self._values: typing.Dict[str, typing.Any] = {}
        if cpu_arch is not None:
            self._values["cpu_arch"] = cpu_arch
        if kubernetes_version is not None:
            self._values["kubernetes_version"] = kubernetes_version
        if node_type is not None:
            self._values["node_type"] = node_type

    @builtins.property
    def cpu_arch(self) -> typing.Optional[CpuArch]:
        """(experimental) What cpu architecture to retrieve the image for (arm64 or x86_64).

        :default: CpuArch.X86_64

        :stability: experimental
        """
        result = self._values.get("cpu_arch")
        return result

    @builtins.property
    def kubernetes_version(self) -> typing.Optional[builtins.str]:
        """(experimental) The Kubernetes version to use.

        :default: - The latest version

        :stability: experimental
        """
        result = self._values.get("kubernetes_version")
        return result

    @builtins.property
    def node_type(self) -> typing.Optional["NodeType"]:
        """(experimental) What instance type to retrieve the image for (standard or GPU-optimized).

        :default: NodeType.STANDARD

        :stability: experimental
        """
        result = self._values.get("node_type")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "EksOptimizedImageProps(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


class EndpointAccess(
    metaclass=jsii.JSIIMeta,
    jsii_type="@aws-cdk/aws-eks.EndpointAccess",
):
    """(experimental) Endpoint access characteristics.

    :stability: experimental
    """

    @jsii.member(jsii_name="onlyFrom")
    def only_from(self, *cidr: builtins.str) -> "EndpointAccess":
        """(experimental) Restrict public access to specific CIDR blocks.

        If public access is disabled, this method will result in an error.

        :param cidr: CIDR blocks.

        :stability: experimental
        """
        return jsii.invoke(self, "onlyFrom", [*cidr])

    @jsii.python.classproperty # type: ignore
    @jsii.member(jsii_name="PRIVATE")
    def PRIVATE(cls) -> "EndpointAccess":
        """(experimental) The cluster endpoint is only accessible through your VPC.

        Worker node traffic to the endpoint will stay within your VPC.

        :stability: experimental
        """
        return jsii.sget(cls, "PRIVATE")

    @jsii.python.classproperty # type: ignore
    @jsii.member(jsii_name="PUBLIC")
    def PUBLIC(cls) -> "EndpointAccess":
        """(experimental) The cluster endpoint is accessible from outside of your VPC.

        Worker node traffic will leave your VPC to connect to the endpoint.

        By default, the endpoint is exposed to all adresses. You can optionally limit the CIDR blocks that can access the public endpoint using the ``PUBLIC.onlyFrom`` method.
        If you limit access to specific CIDR blocks, you must ensure that the CIDR blocks that you
        specify include the addresses that worker nodes and Fargate pods (if you use them)
        access the public endpoint from.

        :stability: experimental
        """
        return jsii.sget(cls, "PUBLIC")

    @jsii.python.classproperty # type: ignore
    @jsii.member(jsii_name="PUBLIC_AND_PRIVATE")
    def PUBLIC_AND_PRIVATE(cls) -> "EndpointAccess":
        """(experimental) The cluster endpoint is accessible from outside of your VPC.

        Worker node traffic to the endpoint will stay within your VPC.

        By default, the endpoint is exposed to all adresses. You can optionally limit the CIDR blocks that can access the public endpoint using the ``PUBLIC_AND_PRIVATE.onlyFrom`` method.
        If you limit access to specific CIDR blocks, you must ensure that the CIDR blocks that you
        specify include the addresses that worker nodes and Fargate pods (if you use them)
        access the public endpoint from.

        :stability: experimental
        """
        return jsii.sget(cls, "PUBLIC_AND_PRIVATE")


@jsii.implements(aws_cdk.core.ITaggable)
class FargateProfile(
    aws_cdk.core.Construct,
    metaclass=jsii.JSIIMeta,
    jsii_type="@aws-cdk/aws-eks.FargateProfile",
):
    """(experimental) Fargate profiles allows an administrator to declare which pods run on Fargate.

    This declaration is done through the profile’s selectors. Each
    profile can have up to five selectors that contain a namespace and optional
    labels. You must define a namespace for every selector. The label field
    consists of multiple optional key-value pairs. Pods that match a selector (by
    matching a namespace for the selector and all of the labels specified in the
    selector) are scheduled on Fargate. If a namespace selector is defined
    without any labels, Amazon EKS will attempt to schedule all pods that run in
    that namespace onto Fargate using the profile. If a to-be-scheduled pod
    matches any of the selectors in the Fargate profile, then that pod is
    scheduled on Fargate.

    If a pod matches multiple Fargate profiles, Amazon EKS picks one of the
    matches at random. In this case, you can specify which profile a pod should
    use by adding the following Kubernetes label to the pod specification:
    eks.amazonaws.com/fargate-profile: profile_name. However, the pod must still
    match a selector in that profile in order to be scheduled onto Fargate.

    :stability: experimental
    """

    def __init__(
        self,
        scope: constructs.Construct,
        id: builtins.str,
        *,
        cluster: "Cluster",
        selectors: typing.List["Selector"],
        fargate_profile_name: typing.Optional[builtins.str] = None,
        pod_execution_role: typing.Optional[aws_cdk.aws_iam.IRole] = None,
        subnet_selection: typing.Optional[aws_cdk.aws_ec2.SubnetSelection] = None,
        vpc: typing.Optional[aws_cdk.aws_ec2.IVpc] = None,
    ) -> None:
        """
        :param scope: -
        :param id: -
        :param cluster: (experimental) The EKS cluster to apply the Fargate profile to. [disable-awslint:ref-via-interface]
        :param selectors: (experimental) The selectors to match for pods to use this Fargate profile. Each selector must have an associated namespace. Optionally, you can also specify labels for a namespace. At least one selector is required and you may specify up to five selectors.
        :param fargate_profile_name: (experimental) The name of the Fargate profile. Default: - generated
        :param pod_execution_role: (experimental) The pod execution role to use for pods that match the selectors in the Fargate profile. The pod execution role allows Fargate infrastructure to register with your cluster as a node, and it provides read access to Amazon ECR image repositories. Default: - a role will be automatically created
        :param subnet_selection: (experimental) Select which subnets to launch your pods into. At this time, pods running on Fargate are not assigned public IP addresses, so only private subnets (with no direct route to an Internet Gateway) are allowed. Default: - all private subnets of the VPC are selected.
        :param vpc: (experimental) The VPC from which to select subnets to launch your pods into. By default, all private subnets are selected. You can customize this using ``subnetSelection``. Default: - all private subnets used by theEKS cluster

        :stability: experimental
        """
        props = FargateProfileProps(
            cluster=cluster,
            selectors=selectors,
            fargate_profile_name=fargate_profile_name,
            pod_execution_role=pod_execution_role,
            subnet_selection=subnet_selection,
            vpc=vpc,
        )

        jsii.create(FargateProfile, self, [scope, id, props])

    @builtins.property # type: ignore
    @jsii.member(jsii_name="fargateProfileArn")
    def fargate_profile_arn(self) -> builtins.str:
        """(experimental) The full Amazon Resource Name (ARN) of the Fargate profile.

        :stability: experimental
        :attribute: true
        """
        return jsii.get(self, "fargateProfileArn")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="fargateProfileName")
    def fargate_profile_name(self) -> builtins.str:
        """(experimental) The name of the Fargate profile.

        :stability: experimental
        :attribute: true
        """
        return jsii.get(self, "fargateProfileName")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="podExecutionRole")
    def pod_execution_role(self) -> aws_cdk.aws_iam.IRole:
        """(experimental) The pod execution role to use for pods that match the selectors in the Fargate profile.

        The pod execution role allows Fargate infrastructure to
        register with your cluster as a node, and it provides read access to Amazon
        ECR image repositories.

        :stability: experimental
        """
        return jsii.get(self, "podExecutionRole")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="tags")
    def tags(self) -> aws_cdk.core.TagManager:
        """(experimental) Resource tags.

        :stability: experimental
        """
        return jsii.get(self, "tags")


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.FargateProfileOptions",
    jsii_struct_bases=[],
    name_mapping={
        "selectors": "selectors",
        "fargate_profile_name": "fargateProfileName",
        "pod_execution_role": "podExecutionRole",
        "subnet_selection": "subnetSelection",
        "vpc": "vpc",
    },
)
class FargateProfileOptions:
    def __init__(
        self,
        *,
        selectors: typing.List["Selector"],
        fargate_profile_name: typing.Optional[builtins.str] = None,
        pod_execution_role: typing.Optional[aws_cdk.aws_iam.IRole] = None,
        subnet_selection: typing.Optional[aws_cdk.aws_ec2.SubnetSelection] = None,
        vpc: typing.Optional[aws_cdk.aws_ec2.IVpc] = None,
    ) -> None:
        """(experimental) Options for defining EKS Fargate Profiles.

        :param selectors: (experimental) The selectors to match for pods to use this Fargate profile. Each selector must have an associated namespace. Optionally, you can also specify labels for a namespace. At least one selector is required and you may specify up to five selectors.
        :param fargate_profile_name: (experimental) The name of the Fargate profile. Default: - generated
        :param pod_execution_role: (experimental) The pod execution role to use for pods that match the selectors in the Fargate profile. The pod execution role allows Fargate infrastructure to register with your cluster as a node, and it provides read access to Amazon ECR image repositories. Default: - a role will be automatically created
        :param subnet_selection: (experimental) Select which subnets to launch your pods into. At this time, pods running on Fargate are not assigned public IP addresses, so only private subnets (with no direct route to an Internet Gateway) are allowed. Default: - all private subnets of the VPC are selected.
        :param vpc: (experimental) The VPC from which to select subnets to launch your pods into. By default, all private subnets are selected. You can customize this using ``subnetSelection``. Default: - all private subnets used by theEKS cluster

        :stability: experimental
        """
        if isinstance(subnet_selection, dict):
            subnet_selection = aws_cdk.aws_ec2.SubnetSelection(**subnet_selection)
        self._values: typing.Dict[str, typing.Any] = {
            "selectors": selectors,
        }
        if fargate_profile_name is not None:
            self._values["fargate_profile_name"] = fargate_profile_name
        if pod_execution_role is not None:
            self._values["pod_execution_role"] = pod_execution_role
        if subnet_selection is not None:
            self._values["subnet_selection"] = subnet_selection
        if vpc is not None:
            self._values["vpc"] = vpc

    @builtins.property
    def selectors(self) -> typing.List["Selector"]:
        """(experimental) The selectors to match for pods to use this Fargate profile.

        Each selector
        must have an associated namespace. Optionally, you can also specify labels
        for a namespace.

        At least one selector is required and you may specify up to five selectors.

        :stability: experimental
        """
        result = self._values.get("selectors")
        assert result is not None, "Required property 'selectors' is missing"
        return result

    @builtins.property
    def fargate_profile_name(self) -> typing.Optional[builtins.str]:
        """(experimental) The name of the Fargate profile.

        :default: - generated

        :stability: experimental
        """
        result = self._values.get("fargate_profile_name")
        return result

    @builtins.property
    def pod_execution_role(self) -> typing.Optional[aws_cdk.aws_iam.IRole]:
        """(experimental) The pod execution role to use for pods that match the selectors in the Fargate profile.

        The pod execution role allows Fargate infrastructure to
        register with your cluster as a node, and it provides read access to Amazon
        ECR image repositories.

        :default: - a role will be automatically created

        :see: https://docs.aws.amazon.com/eks/latest/userguide/pod-execution-role.html
        :stability: experimental
        """
        result = self._values.get("pod_execution_role")
        return result

    @builtins.property
    def subnet_selection(self) -> typing.Optional[aws_cdk.aws_ec2.SubnetSelection]:
        """(experimental) Select which subnets to launch your pods into.

        At this time, pods running
        on Fargate are not assigned public IP addresses, so only private subnets
        (with no direct route to an Internet Gateway) are allowed.

        :default: - all private subnets of the VPC are selected.

        :stability: experimental
        """
        result = self._values.get("subnet_selection")
        return result

    @builtins.property
    def vpc(self) -> typing.Optional[aws_cdk.aws_ec2.IVpc]:
        """(experimental) The VPC from which to select subnets to launch your pods into.

        By default, all private subnets are selected. You can customize this using
        ``subnetSelection``.

        :default: - all private subnets used by theEKS cluster

        :stability: experimental
        """
        result = self._values.get("vpc")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "FargateProfileOptions(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.FargateProfileProps",
    jsii_struct_bases=[FargateProfileOptions],
    name_mapping={
        "selectors": "selectors",
        "fargate_profile_name": "fargateProfileName",
        "pod_execution_role": "podExecutionRole",
        "subnet_selection": "subnetSelection",
        "vpc": "vpc",
        "cluster": "cluster",
    },
)
class FargateProfileProps(FargateProfileOptions):
    def __init__(
        self,
        *,
        selectors: typing.List["Selector"],
        fargate_profile_name: typing.Optional[builtins.str] = None,
        pod_execution_role: typing.Optional[aws_cdk.aws_iam.IRole] = None,
        subnet_selection: typing.Optional[aws_cdk.aws_ec2.SubnetSelection] = None,
        vpc: typing.Optional[aws_cdk.aws_ec2.IVpc] = None,
        cluster: "Cluster",
    ) -> None:
        """(experimental) Configuration props for EKS Fargate Profiles.

        :param selectors: (experimental) The selectors to match for pods to use this Fargate profile. Each selector must have an associated namespace. Optionally, you can also specify labels for a namespace. At least one selector is required and you may specify up to five selectors.
        :param fargate_profile_name: (experimental) The name of the Fargate profile. Default: - generated
        :param pod_execution_role: (experimental) The pod execution role to use for pods that match the selectors in the Fargate profile. The pod execution role allows Fargate infrastructure to register with your cluster as a node, and it provides read access to Amazon ECR image repositories. Default: - a role will be automatically created
        :param subnet_selection: (experimental) Select which subnets to launch your pods into. At this time, pods running on Fargate are not assigned public IP addresses, so only private subnets (with no direct route to an Internet Gateway) are allowed. Default: - all private subnets of the VPC are selected.
        :param vpc: (experimental) The VPC from which to select subnets to launch your pods into. By default, all private subnets are selected. You can customize this using ``subnetSelection``. Default: - all private subnets used by theEKS cluster
        :param cluster: (experimental) The EKS cluster to apply the Fargate profile to. [disable-awslint:ref-via-interface]

        :stability: experimental
        """
        if isinstance(subnet_selection, dict):
            subnet_selection = aws_cdk.aws_ec2.SubnetSelection(**subnet_selection)
        self._values: typing.Dict[str, typing.Any] = {
            "selectors": selectors,
            "cluster": cluster,
        }
        if fargate_profile_name is not None:
            self._values["fargate_profile_name"] = fargate_profile_name
        if pod_execution_role is not None:
            self._values["pod_execution_role"] = pod_execution_role
        if subnet_selection is not None:
            self._values["subnet_selection"] = subnet_selection
        if vpc is not None:
            self._values["vpc"] = vpc

    @builtins.property
    def selectors(self) -> typing.List["Selector"]:
        """(experimental) The selectors to match for pods to use this Fargate profile.

        Each selector
        must have an associated namespace. Optionally, you can also specify labels
        for a namespace.

        At least one selector is required and you may specify up to five selectors.

        :stability: experimental
        """
        result = self._values.get("selectors")
        assert result is not None, "Required property 'selectors' is missing"
        return result

    @builtins.property
    def fargate_profile_name(self) -> typing.Optional[builtins.str]:
        """(experimental) The name of the Fargate profile.

        :default: - generated

        :stability: experimental
        """
        result = self._values.get("fargate_profile_name")
        return result

    @builtins.property
    def pod_execution_role(self) -> typing.Optional[aws_cdk.aws_iam.IRole]:
        """(experimental) The pod execution role to use for pods that match the selectors in the Fargate profile.

        The pod execution role allows Fargate infrastructure to
        register with your cluster as a node, and it provides read access to Amazon
        ECR image repositories.

        :default: - a role will be automatically created

        :see: https://docs.aws.amazon.com/eks/latest/userguide/pod-execution-role.html
        :stability: experimental
        """
        result = self._values.get("pod_execution_role")
        return result

    @builtins.property
    def subnet_selection(self) -> typing.Optional[aws_cdk.aws_ec2.SubnetSelection]:
        """(experimental) Select which subnets to launch your pods into.

        At this time, pods running
        on Fargate are not assigned public IP addresses, so only private subnets
        (with no direct route to an Internet Gateway) are allowed.

        :default: - all private subnets of the VPC are selected.

        :stability: experimental
        """
        result = self._values.get("subnet_selection")
        return result

    @builtins.property
    def vpc(self) -> typing.Optional[aws_cdk.aws_ec2.IVpc]:
        """(experimental) The VPC from which to select subnets to launch your pods into.

        By default, all private subnets are selected. You can customize this using
        ``subnetSelection``.

        :default: - all private subnets used by theEKS cluster

        :stability: experimental
        """
        result = self._values.get("vpc")
        return result

    @builtins.property
    def cluster(self) -> "Cluster":
        """(experimental) The EKS cluster to apply the Fargate profile to.

        [disable-awslint:ref-via-interface]

        :stability: experimental
        """
        result = self._values.get("cluster")
        assert result is not None, "Required property 'cluster' is missing"
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "FargateProfileProps(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


class HelmChart(
    aws_cdk.core.Construct,
    metaclass=jsii.JSIIMeta,
    jsii_type="@aws-cdk/aws-eks.HelmChart",
):
    """(experimental) Represents a helm chart within the Kubernetes system.

    Applies/deletes the resources using ``kubectl`` in sync with the resource.

    :stability: experimental
    """

    def __init__(
        self,
        scope: constructs.Construct,
        id: builtins.str,
        *,
        cluster: "ICluster",
        chart: builtins.str,
        create_namespace: typing.Optional[builtins.bool] = None,
        namespace: typing.Optional[builtins.str] = None,
        release: typing.Optional[builtins.str] = None,
        repository: typing.Optional[builtins.str] = None,
        timeout: typing.Optional[aws_cdk.core.Duration] = None,
        values: typing.Optional[typing.Mapping[builtins.str, typing.Any]] = None,
        version: typing.Optional[builtins.str] = None,
        wait: typing.Optional[builtins.bool] = None,
    ) -> None:
        """
        :param scope: -
        :param id: -
        :param cluster: (experimental) The EKS cluster to apply this configuration to. [disable-awslint:ref-via-interface]
        :param chart: (experimental) The name of the chart.
        :param create_namespace: (experimental) create namespace if not exist. Default: true
        :param namespace: (experimental) The Kubernetes namespace scope of the requests. Default: default
        :param release: (experimental) The name of the release. Default: - If no release name is given, it will use the last 53 characters of the node's unique id.
        :param repository: (experimental) The repository which contains the chart. For example: https://kubernetes-charts.storage.googleapis.com/ Default: - No repository will be used, which means that the chart needs to be an absolute URL.
        :param timeout: (experimental) Amount of time to wait for any individual Kubernetes operation. Maximum 15 minutes. Default: Duration.minutes(5)
        :param values: (experimental) The values to be used by the chart. Default: - No values are provided to the chart.
        :param version: (experimental) The chart version to install. Default: - If this is not specified, the latest version is installed
        :param wait: (experimental) Whether or not Helm should wait until all Pods, PVCs, Services, and minimum number of Pods of a Deployment, StatefulSet, or ReplicaSet are in a ready state before marking the release as successful. Default: - Helm will not wait before marking release as successful

        :stability: experimental
        """
        props = HelmChartProps(
            cluster=cluster,
            chart=chart,
            create_namespace=create_namespace,
            namespace=namespace,
            release=release,
            repository=repository,
            timeout=timeout,
            values=values,
            version=version,
            wait=wait,
        )

        jsii.create(HelmChart, self, [scope, id, props])

    @jsii.python.classproperty # type: ignore
    @jsii.member(jsii_name="RESOURCE_TYPE")
    def RESOURCE_TYPE(cls) -> builtins.str:
        """(experimental) The CloudFormation resource type.

        :stability: experimental
        """
        return jsii.sget(cls, "RESOURCE_TYPE")


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.HelmChartOptions",
    jsii_struct_bases=[],
    name_mapping={
        "chart": "chart",
        "create_namespace": "createNamespace",
        "namespace": "namespace",
        "release": "release",
        "repository": "repository",
        "timeout": "timeout",
        "values": "values",
        "version": "version",
        "wait": "wait",
    },
)
class HelmChartOptions:
    def __init__(
        self,
        *,
        chart: builtins.str,
        create_namespace: typing.Optional[builtins.bool] = None,
        namespace: typing.Optional[builtins.str] = None,
        release: typing.Optional[builtins.str] = None,
        repository: typing.Optional[builtins.str] = None,
        timeout: typing.Optional[aws_cdk.core.Duration] = None,
        values: typing.Optional[typing.Mapping[builtins.str, typing.Any]] = None,
        version: typing.Optional[builtins.str] = None,
        wait: typing.Optional[builtins.bool] = None,
    ) -> None:
        """(experimental) Helm Chart options.

        :param chart: (experimental) The name of the chart.
        :param create_namespace: (experimental) create namespace if not exist. Default: true
        :param namespace: (experimental) The Kubernetes namespace scope of the requests. Default: default
        :param release: (experimental) The name of the release. Default: - If no release name is given, it will use the last 53 characters of the node's unique id.
        :param repository: (experimental) The repository which contains the chart. For example: https://kubernetes-charts.storage.googleapis.com/ Default: - No repository will be used, which means that the chart needs to be an absolute URL.
        :param timeout: (experimental) Amount of time to wait for any individual Kubernetes operation. Maximum 15 minutes. Default: Duration.minutes(5)
        :param values: (experimental) The values to be used by the chart. Default: - No values are provided to the chart.
        :param version: (experimental) The chart version to install. Default: - If this is not specified, the latest version is installed
        :param wait: (experimental) Whether or not Helm should wait until all Pods, PVCs, Services, and minimum number of Pods of a Deployment, StatefulSet, or ReplicaSet are in a ready state before marking the release as successful. Default: - Helm will not wait before marking release as successful

        :stability: experimental
        """
        self._values: typing.Dict[str, typing.Any] = {
            "chart": chart,
        }
        if create_namespace is not None:
            self._values["create_namespace"] = create_namespace
        if namespace is not None:
            self._values["namespace"] = namespace
        if release is not None:
            self._values["release"] = release
        if repository is not None:
            self._values["repository"] = repository
        if timeout is not None:
            self._values["timeout"] = timeout
        if values is not None:
            self._values["values"] = values
        if version is not None:
            self._values["version"] = version
        if wait is not None:
            self._values["wait"] = wait

    @builtins.property
    def chart(self) -> builtins.str:
        """(experimental) The name of the chart.

        :stability: experimental
        """
        result = self._values.get("chart")
        assert result is not None, "Required property 'chart' is missing"
        return result

    @builtins.property
    def create_namespace(self) -> typing.Optional[builtins.bool]:
        """(experimental) create namespace if not exist.

        :default: true

        :stability: experimental
        """
        result = self._values.get("create_namespace")
        return result

    @builtins.property
    def namespace(self) -> typing.Optional[builtins.str]:
        """(experimental) The Kubernetes namespace scope of the requests.

        :default: default

        :stability: experimental
        """
        result = self._values.get("namespace")
        return result

    @builtins.property
    def release(self) -> typing.Optional[builtins.str]:
        """(experimental) The name of the release.

        :default: - If no release name is given, it will use the last 53 characters of the node's unique id.

        :stability: experimental
        """
        result = self._values.get("release")
        return result

    @builtins.property
    def repository(self) -> typing.Optional[builtins.str]:
        """(experimental) The repository which contains the chart.

        For example: https://kubernetes-charts.storage.googleapis.com/

        :default: - No repository will be used, which means that the chart needs to be an absolute URL.

        :stability: experimental
        """
        result = self._values.get("repository")
        return result

    @builtins.property
    def timeout(self) -> typing.Optional[aws_cdk.core.Duration]:
        """(experimental) Amount of time to wait for any individual Kubernetes operation.

        Maximum 15 minutes.

        :default: Duration.minutes(5)

        :stability: experimental
        """
        result = self._values.get("timeout")
        return result

    @builtins.property
    def values(self) -> typing.Optional[typing.Mapping[builtins.str, typing.Any]]:
        """(experimental) The values to be used by the chart.

        :default: - No values are provided to the chart.

        :stability: experimental
        """
        result = self._values.get("values")
        return result

    @builtins.property
    def version(self) -> typing.Optional[builtins.str]:
        """(experimental) The chart version to install.

        :default: - If this is not specified, the latest version is installed

        :stability: experimental
        """
        result = self._values.get("version")
        return result

    @builtins.property
    def wait(self) -> typing.Optional[builtins.bool]:
        """(experimental) Whether or not Helm should wait until all Pods, PVCs, Services, and minimum number of Pods of a Deployment, StatefulSet, or ReplicaSet are in a ready state before marking the release as successful.

        :default: - Helm will not wait before marking release as successful

        :stability: experimental
        """
        result = self._values.get("wait")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "HelmChartOptions(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.HelmChartProps",
    jsii_struct_bases=[HelmChartOptions],
    name_mapping={
        "chart": "chart",
        "create_namespace": "createNamespace",
        "namespace": "namespace",
        "release": "release",
        "repository": "repository",
        "timeout": "timeout",
        "values": "values",
        "version": "version",
        "wait": "wait",
        "cluster": "cluster",
    },
)
class HelmChartProps(HelmChartOptions):
    def __init__(
        self,
        *,
        chart: builtins.str,
        create_namespace: typing.Optional[builtins.bool] = None,
        namespace: typing.Optional[builtins.str] = None,
        release: typing.Optional[builtins.str] = None,
        repository: typing.Optional[builtins.str] = None,
        timeout: typing.Optional[aws_cdk.core.Duration] = None,
        values: typing.Optional[typing.Mapping[builtins.str, typing.Any]] = None,
        version: typing.Optional[builtins.str] = None,
        wait: typing.Optional[builtins.bool] = None,
        cluster: "ICluster",
    ) -> None:
        """(experimental) Helm Chart properties.

        :param chart: (experimental) The name of the chart.
        :param create_namespace: (experimental) create namespace if not exist. Default: true
        :param namespace: (experimental) The Kubernetes namespace scope of the requests. Default: default
        :param release: (experimental) The name of the release. Default: - If no release name is given, it will use the last 53 characters of the node's unique id.
        :param repository: (experimental) The repository which contains the chart. For example: https://kubernetes-charts.storage.googleapis.com/ Default: - No repository will be used, which means that the chart needs to be an absolute URL.
        :param timeout: (experimental) Amount of time to wait for any individual Kubernetes operation. Maximum 15 minutes. Default: Duration.minutes(5)
        :param values: (experimental) The values to be used by the chart. Default: - No values are provided to the chart.
        :param version: (experimental) The chart version to install. Default: - If this is not specified, the latest version is installed
        :param wait: (experimental) Whether or not Helm should wait until all Pods, PVCs, Services, and minimum number of Pods of a Deployment, StatefulSet, or ReplicaSet are in a ready state before marking the release as successful. Default: - Helm will not wait before marking release as successful
        :param cluster: (experimental) The EKS cluster to apply this configuration to. [disable-awslint:ref-via-interface]

        :stability: experimental
        """
        self._values: typing.Dict[str, typing.Any] = {
            "chart": chart,
            "cluster": cluster,
        }
        if create_namespace is not None:
            self._values["create_namespace"] = create_namespace
        if namespace is not None:
            self._values["namespace"] = namespace
        if release is not None:
            self._values["release"] = release
        if repository is not None:
            self._values["repository"] = repository
        if timeout is not None:
            self._values["timeout"] = timeout
        if values is not None:
            self._values["values"] = values
        if version is not None:
            self._values["version"] = version
        if wait is not None:
            self._values["wait"] = wait

    @builtins.property
    def chart(self) -> builtins.str:
        """(experimental) The name of the chart.

        :stability: experimental
        """
        result = self._values.get("chart")
        assert result is not None, "Required property 'chart' is missing"
        return result

    @builtins.property
    def create_namespace(self) -> typing.Optional[builtins.bool]:
        """(experimental) create namespace if not exist.

        :default: true

        :stability: experimental
        """
        result = self._values.get("create_namespace")
        return result

    @builtins.property
    def namespace(self) -> typing.Optional[builtins.str]:
        """(experimental) The Kubernetes namespace scope of the requests.

        :default: default

        :stability: experimental
        """
        result = self._values.get("namespace")
        return result

    @builtins.property
    def release(self) -> typing.Optional[builtins.str]:
        """(experimental) The name of the release.

        :default: - If no release name is given, it will use the last 53 characters of the node's unique id.

        :stability: experimental
        """
        result = self._values.get("release")
        return result

    @builtins.property
    def repository(self) -> typing.Optional[builtins.str]:
        """(experimental) The repository which contains the chart.

        For example: https://kubernetes-charts.storage.googleapis.com/

        :default: - No repository will be used, which means that the chart needs to be an absolute URL.

        :stability: experimental
        """
        result = self._values.get("repository")
        return result

    @builtins.property
    def timeout(self) -> typing.Optional[aws_cdk.core.Duration]:
        """(experimental) Amount of time to wait for any individual Kubernetes operation.

        Maximum 15 minutes.

        :default: Duration.minutes(5)

        :stability: experimental
        """
        result = self._values.get("timeout")
        return result

    @builtins.property
    def values(self) -> typing.Optional[typing.Mapping[builtins.str, typing.Any]]:
        """(experimental) The values to be used by the chart.

        :default: - No values are provided to the chart.

        :stability: experimental
        """
        result = self._values.get("values")
        return result

    @builtins.property
    def version(self) -> typing.Optional[builtins.str]:
        """(experimental) The chart version to install.

        :default: - If this is not specified, the latest version is installed

        :stability: experimental
        """
        result = self._values.get("version")
        return result

    @builtins.property
    def wait(self) -> typing.Optional[builtins.bool]:
        """(experimental) Whether or not Helm should wait until all Pods, PVCs, Services, and minimum number of Pods of a Deployment, StatefulSet, or ReplicaSet are in a ready state before marking the release as successful.

        :default: - Helm will not wait before marking release as successful

        :stability: experimental
        """
        result = self._values.get("wait")
        return result

    @builtins.property
    def cluster(self) -> "ICluster":
        """(experimental) The EKS cluster to apply this configuration to.

        [disable-awslint:ref-via-interface]

        :stability: experimental
        """
        result = self._values.get("cluster")
        assert result is not None, "Required property 'cluster' is missing"
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "HelmChartProps(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


@jsii.interface(jsii_type="@aws-cdk/aws-eks.ICluster")
class ICluster(
    aws_cdk.core.IResource,
    aws_cdk.aws_ec2.IConnectable,
    typing_extensions.Protocol,
):
    """(experimental) An EKS cluster.

    :stability: experimental
    """

    @builtins.staticmethod
    def __jsii_proxy_class__():
        return _IClusterProxy

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterArn")
    def cluster_arn(self) -> builtins.str:
        """(experimental) The unique ARN assigned to the service by AWS in the form of arn:aws:eks:.

        :stability: experimental
        :attribute: true
        """
        ...

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterCertificateAuthorityData")
    def cluster_certificate_authority_data(self) -> builtins.str:
        """(experimental) The certificate-authority-data for your cluster.

        :stability: experimental
        :attribute: true
        """
        ...

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterEncryptionConfigKeyArn")
    def cluster_encryption_config_key_arn(self) -> builtins.str:
        """(experimental) Amazon Resource Name (ARN) or alias of the customer master key (CMK).

        :stability: experimental
        :attribute: true
        """
        ...

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterEndpoint")
    def cluster_endpoint(self) -> builtins.str:
        """(experimental) The API Server endpoint URL.

        :stability: experimental
        :attribute: true
        """
        ...

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterName")
    def cluster_name(self) -> builtins.str:
        """(experimental) The physical name of the Cluster.

        :stability: experimental
        :attribute: true
        """
        ...

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterSecurityGroup")
    def cluster_security_group(self) -> aws_cdk.aws_ec2.ISecurityGroup:
        """(experimental) The cluster security group that was created by Amazon EKS for the cluster.

        :stability: experimental
        :attribute: true
        """
        ...

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterSecurityGroupId")
    def cluster_security_group_id(self) -> builtins.str:
        """(experimental) The id of the cluster security group that was created by Amazon EKS for the cluster.

        :stability: experimental
        :attribute: true
        """
        ...

    @builtins.property # type: ignore
    @jsii.member(jsii_name="openIdConnectProvider")
    def open_id_connect_provider(self) -> aws_cdk.aws_iam.IOpenIdConnectProvider:
        """(experimental) The Open ID Connect Provider of the cluster used to configure Service Accounts.

        :stability: experimental
        """
        ...

    @builtins.property # type: ignore
    @jsii.member(jsii_name="prune")
    def prune(self) -> builtins.bool:
        """(experimental) Indicates whether Kubernetes resources can be automatically pruned.

        When
        this is enabled (default), prune labels will be allocated and injected to
        each resource. These labels will then be used when issuing the ``kubectl apply`` operation with the ``--prune`` switch.

        :stability: experimental
        """
        ...

    @builtins.property # type: ignore
    @jsii.member(jsii_name="vpc")
    def vpc(self) -> aws_cdk.aws_ec2.IVpc:
        """(experimental) The VPC in which this Cluster was created.

        :stability: experimental
        """
        ...

    @builtins.property # type: ignore
    @jsii.member(jsii_name="kubectlEnvironment")
    def kubectl_environment(
        self,
    ) -> typing.Optional[typing.Mapping[builtins.str, builtins.str]]:
        """(experimental) Custom environment variables when running ``kubectl`` against this cluster.

        :stability: experimental
        """
        ...

    @builtins.property # type: ignore
    @jsii.member(jsii_name="kubectlLayer")
    def kubectl_layer(self) -> typing.Optional[aws_cdk.aws_lambda.ILayerVersion]:
        """(experimental) An AWS Lambda layer that includes ``kubectl``, ``helm`` and the ``aws`` CLI.

        If not defined, a default layer will be used.

        :stability: experimental
        """
        ...

    @builtins.property # type: ignore
    @jsii.member(jsii_name="kubectlMemory")
    def kubectl_memory(self) -> typing.Optional[aws_cdk.core.Size]:
        """(experimental) Amount of memory to allocate to the provider's lambda function.

        :stability: experimental
        """
        ...

    @builtins.property # type: ignore
    @jsii.member(jsii_name="kubectlPrivateSubnets")
    def kubectl_private_subnets(
        self,
    ) -> typing.Optional[typing.List[aws_cdk.aws_ec2.ISubnet]]:
        """(experimental) Subnets to host the ``kubectl`` compute resources.

        If this is undefined, the k8s endpoint is expected to be accessible
        publicly.

        :stability: experimental
        """
        ...

    @builtins.property # type: ignore
    @jsii.member(jsii_name="kubectlRole")
    def kubectl_role(self) -> typing.Optional[aws_cdk.aws_iam.IRole]:
        """(experimental) An IAM role that can perform kubectl operations against this cluster.

        The role should be mapped to the ``system:masters`` Kubernetes RBAC role.

        :stability: experimental
        """
        ...

    @builtins.property # type: ignore
    @jsii.member(jsii_name="kubectlSecurityGroup")
    def kubectl_security_group(self) -> typing.Optional[aws_cdk.aws_ec2.ISecurityGroup]:
        """(experimental) A security group to use for ``kubectl`` execution.

        If this is undefined, the k8s endpoint is expected to be accessible
        publicly.

        :stability: experimental
        """
        ...

    @jsii.member(jsii_name="addCdk8sChart")
    def add_cdk8s_chart(
        self,
        id: builtins.str,
        chart: constructs.Construct,
    ) -> "KubernetesManifest":
        """(experimental) Defines a CDK8s chart in this cluster.

        :param id: logical id of this chart.
        :param chart: the cdk8s chart.

        :return: a ``KubernetesManifest`` construct representing the chart.

        :stability: experimental
        """
        ...

    @jsii.member(jsii_name="addHelmChart")
    def add_helm_chart(
        self,
        id: builtins.str,
        *,
        chart: builtins.str,
        create_namespace: typing.Optional[builtins.bool] = None,
        namespace: typing.Optional[builtins.str] = None,
        release: typing.Optional[builtins.str] = None,
        repository: typing.Optional[builtins.str] = None,
        timeout: typing.Optional[aws_cdk.core.Duration] = None,
        values: typing.Optional[typing.Mapping[builtins.str, typing.Any]] = None,
        version: typing.Optional[builtins.str] = None,
        wait: typing.Optional[builtins.bool] = None,
    ) -> HelmChart:
        """(experimental) Defines a Helm chart in this cluster.

        :param id: logical id of this chart.
        :param chart: (experimental) The name of the chart.
        :param create_namespace: (experimental) create namespace if not exist. Default: true
        :param namespace: (experimental) The Kubernetes namespace scope of the requests. Default: default
        :param release: (experimental) The name of the release. Default: - If no release name is given, it will use the last 53 characters of the node's unique id.
        :param repository: (experimental) The repository which contains the chart. For example: https://kubernetes-charts.storage.googleapis.com/ Default: - No repository will be used, which means that the chart needs to be an absolute URL.
        :param timeout: (experimental) Amount of time to wait for any individual Kubernetes operation. Maximum 15 minutes. Default: Duration.minutes(5)
        :param values: (experimental) The values to be used by the chart. Default: - No values are provided to the chart.
        :param version: (experimental) The chart version to install. Default: - If this is not specified, the latest version is installed
        :param wait: (experimental) Whether or not Helm should wait until all Pods, PVCs, Services, and minimum number of Pods of a Deployment, StatefulSet, or ReplicaSet are in a ready state before marking the release as successful. Default: - Helm will not wait before marking release as successful

        :return: a ``HelmChart`` construct

        :stability: experimental
        """
        ...

    @jsii.member(jsii_name="addManifest")
    def add_manifest(
        self,
        id: builtins.str,
        *manifest: typing.Mapping[builtins.str, typing.Any],
    ) -> "KubernetesManifest":
        """(experimental) Defines a Kubernetes resource in this cluster.

        The manifest will be applied/deleted using kubectl as needed.

        :param id: logical id of this manifest.
        :param manifest: a list of Kubernetes resource specifications.

        :return: a ``KubernetesManifest`` object.

        :stability: experimental
        """
        ...

    @jsii.member(jsii_name="addServiceAccount")
    def add_service_account(
        self,
        id: builtins.str,
        *,
        name: typing.Optional[builtins.str] = None,
        namespace: typing.Optional[builtins.str] = None,
    ) -> "ServiceAccount":
        """(experimental) Creates a new service account with corresponding IAM Role (IRSA).

        :param id: logical id of service account.
        :param name: (experimental) The name of the service account. Default: - If no name is given, it will use the id of the resource.
        :param namespace: (experimental) The namespace of the service account. Default: "default"

        :stability: experimental
        """
        ...


class _IClusterProxy(
    jsii.proxy_for(aws_cdk.core.IResource), # type: ignore
    jsii.proxy_for(aws_cdk.aws_ec2.IConnectable), # type: ignore
):
    """(experimental) An EKS cluster.

    :stability: experimental
    """

    __jsii_type__: typing.ClassVar[str] = "@aws-cdk/aws-eks.ICluster"

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterArn")
    def cluster_arn(self) -> builtins.str:
        """(experimental) The unique ARN assigned to the service by AWS in the form of arn:aws:eks:.

        :stability: experimental
        :attribute: true
        """
        return jsii.get(self, "clusterArn")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterCertificateAuthorityData")
    def cluster_certificate_authority_data(self) -> builtins.str:
        """(experimental) The certificate-authority-data for your cluster.

        :stability: experimental
        :attribute: true
        """
        return jsii.get(self, "clusterCertificateAuthorityData")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterEncryptionConfigKeyArn")
    def cluster_encryption_config_key_arn(self) -> builtins.str:
        """(experimental) Amazon Resource Name (ARN) or alias of the customer master key (CMK).

        :stability: experimental
        :attribute: true
        """
        return jsii.get(self, "clusterEncryptionConfigKeyArn")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterEndpoint")
    def cluster_endpoint(self) -> builtins.str:
        """(experimental) The API Server endpoint URL.

        :stability: experimental
        :attribute: true
        """
        return jsii.get(self, "clusterEndpoint")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterName")
    def cluster_name(self) -> builtins.str:
        """(experimental) The physical name of the Cluster.

        :stability: experimental
        :attribute: true
        """
        return jsii.get(self, "clusterName")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterSecurityGroup")
    def cluster_security_group(self) -> aws_cdk.aws_ec2.ISecurityGroup:
        """(experimental) The cluster security group that was created by Amazon EKS for the cluster.

        :stability: experimental
        :attribute: true
        """
        return jsii.get(self, "clusterSecurityGroup")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterSecurityGroupId")
    def cluster_security_group_id(self) -> builtins.str:
        """(experimental) The id of the cluster security group that was created by Amazon EKS for the cluster.

        :stability: experimental
        :attribute: true
        """
        return jsii.get(self, "clusterSecurityGroupId")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="openIdConnectProvider")
    def open_id_connect_provider(self) -> aws_cdk.aws_iam.IOpenIdConnectProvider:
        """(experimental) The Open ID Connect Provider of the cluster used to configure Service Accounts.

        :stability: experimental
        """
        return jsii.get(self, "openIdConnectProvider")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="prune")
    def prune(self) -> builtins.bool:
        """(experimental) Indicates whether Kubernetes resources can be automatically pruned.

        When
        this is enabled (default), prune labels will be allocated and injected to
        each resource. These labels will then be used when issuing the ``kubectl apply`` operation with the ``--prune`` switch.

        :stability: experimental
        """
        return jsii.get(self, "prune")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="vpc")
    def vpc(self) -> aws_cdk.aws_ec2.IVpc:
        """(experimental) The VPC in which this Cluster was created.

        :stability: experimental
        """
        return jsii.get(self, "vpc")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="kubectlEnvironment")
    def kubectl_environment(
        self,
    ) -> typing.Optional[typing.Mapping[builtins.str, builtins.str]]:
        """(experimental) Custom environment variables when running ``kubectl`` against this cluster.

        :stability: experimental
        """
        return jsii.get(self, "kubectlEnvironment")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="kubectlLayer")
    def kubectl_layer(self) -> typing.Optional[aws_cdk.aws_lambda.ILayerVersion]:
        """(experimental) An AWS Lambda layer that includes ``kubectl``, ``helm`` and the ``aws`` CLI.

        If not defined, a default layer will be used.

        :stability: experimental
        """
        return jsii.get(self, "kubectlLayer")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="kubectlMemory")
    def kubectl_memory(self) -> typing.Optional[aws_cdk.core.Size]:
        """(experimental) Amount of memory to allocate to the provider's lambda function.

        :stability: experimental
        """
        return jsii.get(self, "kubectlMemory")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="kubectlPrivateSubnets")
    def kubectl_private_subnets(
        self,
    ) -> typing.Optional[typing.List[aws_cdk.aws_ec2.ISubnet]]:
        """(experimental) Subnets to host the ``kubectl`` compute resources.

        If this is undefined, the k8s endpoint is expected to be accessible
        publicly.

        :stability: experimental
        """
        return jsii.get(self, "kubectlPrivateSubnets")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="kubectlRole")
    def kubectl_role(self) -> typing.Optional[aws_cdk.aws_iam.IRole]:
        """(experimental) An IAM role that can perform kubectl operations against this cluster.

        The role should be mapped to the ``system:masters`` Kubernetes RBAC role.

        :stability: experimental
        """
        return jsii.get(self, "kubectlRole")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="kubectlSecurityGroup")
    def kubectl_security_group(self) -> typing.Optional[aws_cdk.aws_ec2.ISecurityGroup]:
        """(experimental) A security group to use for ``kubectl`` execution.

        If this is undefined, the k8s endpoint is expected to be accessible
        publicly.

        :stability: experimental
        """
        return jsii.get(self, "kubectlSecurityGroup")

    @jsii.member(jsii_name="addCdk8sChart")
    def add_cdk8s_chart(
        self,
        id: builtins.str,
        chart: constructs.Construct,
    ) -> "KubernetesManifest":
        """(experimental) Defines a CDK8s chart in this cluster.

        :param id: logical id of this chart.
        :param chart: the cdk8s chart.

        :return: a ``KubernetesManifest`` construct representing the chart.

        :stability: experimental
        """
        return jsii.invoke(self, "addCdk8sChart", [id, chart])

    @jsii.member(jsii_name="addHelmChart")
    def add_helm_chart(
        self,
        id: builtins.str,
        *,
        chart: builtins.str,
        create_namespace: typing.Optional[builtins.bool] = None,
        namespace: typing.Optional[builtins.str] = None,
        release: typing.Optional[builtins.str] = None,
        repository: typing.Optional[builtins.str] = None,
        timeout: typing.Optional[aws_cdk.core.Duration] = None,
        values: typing.Optional[typing.Mapping[builtins.str, typing.Any]] = None,
        version: typing.Optional[builtins.str] = None,
        wait: typing.Optional[builtins.bool] = None,
    ) -> HelmChart:
        """(experimental) Defines a Helm chart in this cluster.

        :param id: logical id of this chart.
        :param chart: (experimental) The name of the chart.
        :param create_namespace: (experimental) create namespace if not exist. Default: true
        :param namespace: (experimental) The Kubernetes namespace scope of the requests. Default: default
        :param release: (experimental) The name of the release. Default: - If no release name is given, it will use the last 53 characters of the node's unique id.
        :param repository: (experimental) The repository which contains the chart. For example: https://kubernetes-charts.storage.googleapis.com/ Default: - No repository will be used, which means that the chart needs to be an absolute URL.
        :param timeout: (experimental) Amount of time to wait for any individual Kubernetes operation. Maximum 15 minutes. Default: Duration.minutes(5)
        :param values: (experimental) The values to be used by the chart. Default: - No values are provided to the chart.
        :param version: (experimental) The chart version to install. Default: - If this is not specified, the latest version is installed
        :param wait: (experimental) Whether or not Helm should wait until all Pods, PVCs, Services, and minimum number of Pods of a Deployment, StatefulSet, or ReplicaSet are in a ready state before marking the release as successful. Default: - Helm will not wait before marking release as successful

        :return: a ``HelmChart`` construct

        :stability: experimental
        """
        options = HelmChartOptions(
            chart=chart,
            create_namespace=create_namespace,
            namespace=namespace,
            release=release,
            repository=repository,
            timeout=timeout,
            values=values,
            version=version,
            wait=wait,
        )

        return jsii.invoke(self, "addHelmChart", [id, options])

    @jsii.member(jsii_name="addManifest")
    def add_manifest(
        self,
        id: builtins.str,
        *manifest: typing.Mapping[builtins.str, typing.Any],
    ) -> "KubernetesManifest":
        """(experimental) Defines a Kubernetes resource in this cluster.

        The manifest will be applied/deleted using kubectl as needed.

        :param id: logical id of this manifest.
        :param manifest: a list of Kubernetes resource specifications.

        :return: a ``KubernetesManifest`` object.

        :stability: experimental
        """
        return jsii.invoke(self, "addManifest", [id, *manifest])

    @jsii.member(jsii_name="addServiceAccount")
    def add_service_account(
        self,
        id: builtins.str,
        *,
        name: typing.Optional[builtins.str] = None,
        namespace: typing.Optional[builtins.str] = None,
    ) -> "ServiceAccount":
        """(experimental) Creates a new service account with corresponding IAM Role (IRSA).

        :param id: logical id of service account.
        :param name: (experimental) The name of the service account. Default: - If no name is given, it will use the id of the resource.
        :param namespace: (experimental) The namespace of the service account. Default: "default"

        :stability: experimental
        """
        options = ServiceAccountOptions(name=name, namespace=namespace)

        return jsii.invoke(self, "addServiceAccount", [id, options])


@jsii.interface(jsii_type="@aws-cdk/aws-eks.INodegroup")
class INodegroup(aws_cdk.core.IResource, typing_extensions.Protocol):
    """(experimental) NodeGroup interface.

    :stability: experimental
    """

    @builtins.staticmethod
    def __jsii_proxy_class__():
        return _INodegroupProxy

    @builtins.property # type: ignore
    @jsii.member(jsii_name="nodegroupName")
    def nodegroup_name(self) -> builtins.str:
        """(experimental) Name of the nodegroup.

        :stability: experimental
        :attribute: true
        """
        ...


class _INodegroupProxy(
    jsii.proxy_for(aws_cdk.core.IResource) # type: ignore
):
    """(experimental) NodeGroup interface.

    :stability: experimental
    """

    __jsii_type__: typing.ClassVar[str] = "@aws-cdk/aws-eks.INodegroup"

    @builtins.property # type: ignore
    @jsii.member(jsii_name="nodegroupName")
    def nodegroup_name(self) -> builtins.str:
        """(experimental) Name of the nodegroup.

        :stability: experimental
        :attribute: true
        """
        return jsii.get(self, "nodegroupName")


@jsii.implements(aws_cdk.aws_lambda.ILayerVersion)
class KubectlLayer(
    aws_cdk.core.Construct,
    metaclass=jsii.JSIIMeta,
    jsii_type="@aws-cdk/aws-eks.KubectlLayer",
):
    """(experimental) An AWS Lambda layer that includes kubectl and the AWS CLI.

    :see: https://github.com/aws-samples/aws-lambda-layer-kubectl
    :stability: experimental
    """

    def __init__(
        self,
        scope: constructs.Construct,
        id: builtins.str,
        *,
        application_id: typing.Optional[builtins.str] = None,
        version: typing.Optional[builtins.str] = None,
    ) -> None:
        """
        :param scope: -
        :param id: -
        :param application_id: (experimental) The Serverless Application Repository application ID which contains the kubectl layer. Default: - The ARN for the ``lambda-layer-kubectl`` SAR app.
        :param version: (experimental) The semantic version of the kubectl AWS Lambda Layer SAR app to use. Default: '2.0.0'

        :stability: experimental
        """
        props = KubectlLayerProps(application_id=application_id, version=version)

        jsii.create(KubectlLayer, self, [scope, id, props])

    @jsii.member(jsii_name="addPermission")
    def add_permission(
        self,
        _id: builtins.str,
        *,
        account_id: builtins.str,
        organization_id: typing.Optional[builtins.str] = None,
    ) -> None:
        """(experimental) Add permission for this layer version to specific entities.

        Usage within
        the same account where the layer is defined is always allowed and does not
        require calling this method. Note that the principal that creates the
        Lambda function using the layer (for example, a CloudFormation changeset
        execution role) also needs to have the ``lambda:GetLayerVersion``
        permission on the layer version.

        :param _id: -
        :param account_id: The AWS Account id of the account that is authorized to use a Lambda Layer Version. The wild-card ``'*'`` can be used to grant access to "any" account (or any account in an organization when ``organizationId`` is specified).
        :param organization_id: The ID of the AWS Organization to which the grant is restricted. Can only be specified if ``accountId`` is ``'*'``

        :stability: experimental
        """
        _permission = aws_cdk.aws_lambda.LayerVersionPermission(
            account_id=account_id, organization_id=organization_id
        )

        return jsii.invoke(self, "addPermission", [_id, _permission])

    @builtins.property # type: ignore
    @jsii.member(jsii_name="env")
    def env(self) -> aws_cdk.core.ResourceEnvironment:
        """(experimental) The environment this resource belongs to.

        For resources that are created and managed by the CDK
        (generally, those created by creating new class instances like Role, Bucket, etc.),
        this is always the same as the environment of the stack they belong to;
        however, for imported resources
        (those obtained from static methods like fromRoleArn, fromBucketName, etc.),
        that might be different than the stack they were imported into.

        :stability: experimental
        """
        return jsii.get(self, "env")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="layerVersionArn")
    def layer_version_arn(self) -> builtins.str:
        """(experimental) The ARN of the AWS Lambda layer version.

        :stability: experimental
        """
        return jsii.get(self, "layerVersionArn")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="stack")
    def stack(self) -> aws_cdk.core.Stack:
        """(experimental) The stack in which this resource is defined.

        :stability: experimental
        """
        return jsii.get(self, "stack")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="compatibleRuntimes")
    def compatible_runtimes(
        self,
    ) -> typing.Optional[typing.List[aws_cdk.aws_lambda.Runtime]]:
        """(experimental) All runtimes are compatible.

        :stability: experimental
        """
        return jsii.get(self, "compatibleRuntimes")


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.KubectlLayerProps",
    jsii_struct_bases=[],
    name_mapping={"application_id": "applicationId", "version": "version"},
)
class KubectlLayerProps:
    def __init__(
        self,
        *,
        application_id: typing.Optional[builtins.str] = None,
        version: typing.Optional[builtins.str] = None,
    ) -> None:
        """(experimental) Properties for KubectlLayer.

        :param application_id: (experimental) The Serverless Application Repository application ID which contains the kubectl layer. Default: - The ARN for the ``lambda-layer-kubectl`` SAR app.
        :param version: (experimental) The semantic version of the kubectl AWS Lambda Layer SAR app to use. Default: '2.0.0'

        :stability: experimental
        """
        self._values: typing.Dict[str, typing.Any] = {}
        if application_id is not None:
            self._values["application_id"] = application_id
        if version is not None:
            self._values["version"] = version

    @builtins.property
    def application_id(self) -> typing.Optional[builtins.str]:
        """(experimental) The Serverless Application Repository application ID which contains the kubectl layer.

        :default: - The ARN for the ``lambda-layer-kubectl`` SAR app.

        :see: https://github.com/aws-samples/aws-lambda-layer-kubectl
        :stability: experimental
        """
        result = self._values.get("application_id")
        return result

    @builtins.property
    def version(self) -> typing.Optional[builtins.str]:
        """(experimental) The semantic version of the kubectl AWS Lambda Layer SAR app to use.

        :default: '2.0.0'

        :stability: experimental
        """
        result = self._values.get("version")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "KubectlLayerProps(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


class KubernetesManifest(
    aws_cdk.core.Construct,
    metaclass=jsii.JSIIMeta,
    jsii_type="@aws-cdk/aws-eks.KubernetesManifest",
):
    """(experimental) Represents a manifest within the Kubernetes system.

    Alternatively, you can use ``cluster.addManifest(resource[, resource, ...])``
    to define resources on this cluster.

    Applies/deletes the manifest using ``kubectl``.

    :stability: experimental
    """

    def __init__(
        self,
        scope: constructs.Construct,
        id: builtins.str,
        *,
        cluster: ICluster,
        manifest: typing.List[typing.Mapping[builtins.str, typing.Any]],
        overwrite: typing.Optional[builtins.bool] = None,
        prune: typing.Optional[builtins.bool] = None,
    ) -> None:
        """
        :param scope: -
        :param id: -
        :param cluster: (experimental) The EKS cluster to apply this manifest to. [disable-awslint:ref-via-interface]
        :param manifest: (experimental) The manifest to apply. Consists of any number of child resources. When the resources are created/updated, this manifest will be applied to the cluster through ``kubectl apply`` and when the resources or the stack is deleted, the resources in the manifest will be deleted through ``kubectl delete``.
        :param overwrite: (experimental) Overwrite any existing resources. If this is set, we will use ``kubectl apply`` instead of ``kubectl create`` when the resource is created. Otherwise, if there is already a resource in the cluster with the same name, the operation will fail. Default: false
        :param prune: (experimental) When a resource is removed from a Kubernetes manifest, it no longer appears in the manifest, and there is no way to know that this resource needs to be deleted. To address this, ``kubectl apply`` has a ``--prune`` option which will query the cluster for all resources with a specific label and will remove all the labeld resources that are not part of the applied manifest. If this option is disabled and a resource is removed, it will become "orphaned" and will not be deleted from the cluster. When this option is enabled (default), the construct will inject a label to all Kubernetes resources included in this manifest which will be used to prune resources when the manifest changes via ``kubectl apply --prune``. The label name will be ``aws.cdk.eks/prune-<ADDR>`` where ``<ADDR>`` is the 42-char unique address of this construct in the construct tree. Value is empty. Default: - based on the prune option of the cluster, which is ``true`` unless otherwise specified.

        :stability: experimental
        """
        props = KubernetesManifestProps(
            cluster=cluster, manifest=manifest, overwrite=overwrite, prune=prune
        )

        jsii.create(KubernetesManifest, self, [scope, id, props])

    @jsii.python.classproperty # type: ignore
    @jsii.member(jsii_name="RESOURCE_TYPE")
    def RESOURCE_TYPE(cls) -> builtins.str:
        """(experimental) The CloudFormation reosurce type.

        :stability: experimental
        """
        return jsii.sget(cls, "RESOURCE_TYPE")


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.KubernetesManifestOptions",
    jsii_struct_bases=[],
    name_mapping={"prune": "prune"},
)
class KubernetesManifestOptions:
    def __init__(self, *, prune: typing.Optional[builtins.bool] = None) -> None:
        """(experimental) Options for ``KubernetesManifest``.

        :param prune: (experimental) When a resource is removed from a Kubernetes manifest, it no longer appears in the manifest, and there is no way to know that this resource needs to be deleted. To address this, ``kubectl apply`` has a ``--prune`` option which will query the cluster for all resources with a specific label and will remove all the labeld resources that are not part of the applied manifest. If this option is disabled and a resource is removed, it will become "orphaned" and will not be deleted from the cluster. When this option is enabled (default), the construct will inject a label to all Kubernetes resources included in this manifest which will be used to prune resources when the manifest changes via ``kubectl apply --prune``. The label name will be ``aws.cdk.eks/prune-<ADDR>`` where ``<ADDR>`` is the 42-char unique address of this construct in the construct tree. Value is empty. Default: - based on the prune option of the cluster, which is ``true`` unless otherwise specified.

        :stability: experimental
        """
        self._values: typing.Dict[str, typing.Any] = {}
        if prune is not None:
            self._values["prune"] = prune

    @builtins.property
    def prune(self) -> typing.Optional[builtins.bool]:
        """(experimental) When a resource is removed from a Kubernetes manifest, it no longer appears in the manifest, and there is no way to know that this resource needs to be deleted.

        To address this, ``kubectl apply`` has a ``--prune`` option which will
        query the cluster for all resources with a specific label and will remove
        all the labeld resources that are not part of the applied manifest. If this
        option is disabled and a resource is removed, it will become "orphaned" and
        will not be deleted from the cluster.

        When this option is enabled (default), the construct will inject a label to
        all Kubernetes resources included in this manifest which will be used to
        prune resources when the manifest changes via ``kubectl apply --prune``.

        The label name will be ``aws.cdk.eks/prune-<ADDR>`` where ``<ADDR>`` is the
        42-char unique address of this construct in the construct tree. Value is
        empty.

        :default:

        - based on the prune option of the cluster, which is ``true`` unless
        otherwise specified.

        :see: https://kubernetes.io/docs/tasks/manage-kubernetes-objects/declarative-config/#alternative-kubectl-apply-f-directory-prune-l-your-label
        :stability: experimental
        """
        result = self._values.get("prune")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "KubernetesManifestOptions(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.KubernetesManifestProps",
    jsii_struct_bases=[KubernetesManifestOptions],
    name_mapping={
        "prune": "prune",
        "cluster": "cluster",
        "manifest": "manifest",
        "overwrite": "overwrite",
    },
)
class KubernetesManifestProps(KubernetesManifestOptions):
    def __init__(
        self,
        *,
        prune: typing.Optional[builtins.bool] = None,
        cluster: ICluster,
        manifest: typing.List[typing.Mapping[builtins.str, typing.Any]],
        overwrite: typing.Optional[builtins.bool] = None,
    ) -> None:
        """(experimental) Properties for KubernetesManifest.

        :param prune: (experimental) When a resource is removed from a Kubernetes manifest, it no longer appears in the manifest, and there is no way to know that this resource needs to be deleted. To address this, ``kubectl apply`` has a ``--prune`` option which will query the cluster for all resources with a specific label and will remove all the labeld resources that are not part of the applied manifest. If this option is disabled and a resource is removed, it will become "orphaned" and will not be deleted from the cluster. When this option is enabled (default), the construct will inject a label to all Kubernetes resources included in this manifest which will be used to prune resources when the manifest changes via ``kubectl apply --prune``. The label name will be ``aws.cdk.eks/prune-<ADDR>`` where ``<ADDR>`` is the 42-char unique address of this construct in the construct tree. Value is empty. Default: - based on the prune option of the cluster, which is ``true`` unless otherwise specified.
        :param cluster: (experimental) The EKS cluster to apply this manifest to. [disable-awslint:ref-via-interface]
        :param manifest: (experimental) The manifest to apply. Consists of any number of child resources. When the resources are created/updated, this manifest will be applied to the cluster through ``kubectl apply`` and when the resources or the stack is deleted, the resources in the manifest will be deleted through ``kubectl delete``.
        :param overwrite: (experimental) Overwrite any existing resources. If this is set, we will use ``kubectl apply`` instead of ``kubectl create`` when the resource is created. Otherwise, if there is already a resource in the cluster with the same name, the operation will fail. Default: false

        :stability: experimental
        """
        self._values: typing.Dict[str, typing.Any] = {
            "cluster": cluster,
            "manifest": manifest,
        }
        if prune is not None:
            self._values["prune"] = prune
        if overwrite is not None:
            self._values["overwrite"] = overwrite

    @builtins.property
    def prune(self) -> typing.Optional[builtins.bool]:
        """(experimental) When a resource is removed from a Kubernetes manifest, it no longer appears in the manifest, and there is no way to know that this resource needs to be deleted.

        To address this, ``kubectl apply`` has a ``--prune`` option which will
        query the cluster for all resources with a specific label and will remove
        all the labeld resources that are not part of the applied manifest. If this
        option is disabled and a resource is removed, it will become "orphaned" and
        will not be deleted from the cluster.

        When this option is enabled (default), the construct will inject a label to
        all Kubernetes resources included in this manifest which will be used to
        prune resources when the manifest changes via ``kubectl apply --prune``.

        The label name will be ``aws.cdk.eks/prune-<ADDR>`` where ``<ADDR>`` is the
        42-char unique address of this construct in the construct tree. Value is
        empty.

        :default:

        - based on the prune option of the cluster, which is ``true`` unless
        otherwise specified.

        :see: https://kubernetes.io/docs/tasks/manage-kubernetes-objects/declarative-config/#alternative-kubectl-apply-f-directory-prune-l-your-label
        :stability: experimental
        """
        result = self._values.get("prune")
        return result

    @builtins.property
    def cluster(self) -> ICluster:
        """(experimental) The EKS cluster to apply this manifest to.

        [disable-awslint:ref-via-interface]

        :stability: experimental
        """
        result = self._values.get("cluster")
        assert result is not None, "Required property 'cluster' is missing"
        return result

    @builtins.property
    def manifest(self) -> typing.List[typing.Mapping[builtins.str, typing.Any]]:
        """(experimental) The manifest to apply.

        Consists of any number of child resources.

        When the resources are created/updated, this manifest will be applied to the
        cluster through ``kubectl apply`` and when the resources or the stack is
        deleted, the resources in the manifest will be deleted through ``kubectl delete``.

        :stability: experimental

        Example::

            # Example automatically generated. See https://github.com/aws/jsii/issues/826
            [{
                "api_version": "v1",
                "kind": "Pod",
                "metadata": {"name": "mypod"},
                "spec": {
                    "containers": [{"name": "hello", "image": "paulbouwer/hello-kubernetes:1.5", "ports": [{"container_port": 8080}]}]
                }
            }]
        """
        result = self._values.get("manifest")
        assert result is not None, "Required property 'manifest' is missing"
        return result

    @builtins.property
    def overwrite(self) -> typing.Optional[builtins.bool]:
        """(experimental) Overwrite any existing resources.

        If this is set, we will use ``kubectl apply`` instead of ``kubectl create``
        when the resource is created. Otherwise, if there is already a resource
        in the cluster with the same name, the operation will fail.

        :default: false

        :stability: experimental
        """
        result = self._values.get("overwrite")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "KubernetesManifestProps(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


class KubernetesObjectValue(
    aws_cdk.core.Construct,
    metaclass=jsii.JSIIMeta,
    jsii_type="@aws-cdk/aws-eks.KubernetesObjectValue",
):
    """(experimental) Represents a value of a specific object deployed in the cluster.

    Use this to fetch any information available by the ``kubectl get`` command.

    :stability: experimental
    """

    def __init__(
        self,
        scope: constructs.Construct,
        id: builtins.str,
        *,
        cluster: ICluster,
        json_path: builtins.str,
        object_name: builtins.str,
        object_type: builtins.str,
        object_namespace: typing.Optional[builtins.str] = None,
        timeout: typing.Optional[aws_cdk.core.Duration] = None,
    ) -> None:
        """
        :param scope: -
        :param id: -
        :param cluster: (experimental) The EKS cluster to fetch attributes from. [disable-awslint:ref-via-interface]
        :param json_path: (experimental) JSONPath to the specific value.
        :param object_name: (experimental) The name of the object to query.
        :param object_type: (experimental) The object type to query. (e.g 'service', 'pod'...)
        :param object_namespace: (experimental) The namespace the object belongs to. Default: 'default'
        :param timeout: (experimental) Timeout for waiting on a value. Default: Duration.minutes(5)

        :stability: experimental
        """
        props = KubernetesObjectValueProps(
            cluster=cluster,
            json_path=json_path,
            object_name=object_name,
            object_type=object_type,
            object_namespace=object_namespace,
            timeout=timeout,
        )

        jsii.create(KubernetesObjectValue, self, [scope, id, props])

    @jsii.python.classproperty # type: ignore
    @jsii.member(jsii_name="RESOURCE_TYPE")
    def RESOURCE_TYPE(cls) -> builtins.str:
        """(experimental) The CloudFormation reosurce type.

        :stability: experimental
        """
        return jsii.sget(cls, "RESOURCE_TYPE")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="value")
    def value(self) -> builtins.str:
        """(experimental) The value as a string token.

        :stability: experimental
        """
        return jsii.get(self, "value")


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.KubernetesObjectValueProps",
    jsii_struct_bases=[],
    name_mapping={
        "cluster": "cluster",
        "json_path": "jsonPath",
        "object_name": "objectName",
        "object_type": "objectType",
        "object_namespace": "objectNamespace",
        "timeout": "timeout",
    },
)
class KubernetesObjectValueProps:
    def __init__(
        self,
        *,
        cluster: ICluster,
        json_path: builtins.str,
        object_name: builtins.str,
        object_type: builtins.str,
        object_namespace: typing.Optional[builtins.str] = None,
        timeout: typing.Optional[aws_cdk.core.Duration] = None,
    ) -> None:
        """(experimental) Properties for KubernetesObjectValue.

        :param cluster: (experimental) The EKS cluster to fetch attributes from. [disable-awslint:ref-via-interface]
        :param json_path: (experimental) JSONPath to the specific value.
        :param object_name: (experimental) The name of the object to query.
        :param object_type: (experimental) The object type to query. (e.g 'service', 'pod'...)
        :param object_namespace: (experimental) The namespace the object belongs to. Default: 'default'
        :param timeout: (experimental) Timeout for waiting on a value. Default: Duration.minutes(5)

        :stability: experimental
        """
        self._values: typing.Dict[str, typing.Any] = {
            "cluster": cluster,
            "json_path": json_path,
            "object_name": object_name,
            "object_type": object_type,
        }
        if object_namespace is not None:
            self._values["object_namespace"] = object_namespace
        if timeout is not None:
            self._values["timeout"] = timeout

    @builtins.property
    def cluster(self) -> ICluster:
        """(experimental) The EKS cluster to fetch attributes from.

        [disable-awslint:ref-via-interface]

        :stability: experimental
        """
        result = self._values.get("cluster")
        assert result is not None, "Required property 'cluster' is missing"
        return result

    @builtins.property
    def json_path(self) -> builtins.str:
        """(experimental) JSONPath to the specific value.

        :see: https://kubernetes.io/docs/reference/kubectl/jsonpath/
        :stability: experimental
        """
        result = self._values.get("json_path")
        assert result is not None, "Required property 'json_path' is missing"
        return result

    @builtins.property
    def object_name(self) -> builtins.str:
        """(experimental) The name of the object to query.

        :stability: experimental
        """
        result = self._values.get("object_name")
        assert result is not None, "Required property 'object_name' is missing"
        return result

    @builtins.property
    def object_type(self) -> builtins.str:
        """(experimental) The object type to query.

        (e.g 'service', 'pod'...)

        :stability: experimental
        """
        result = self._values.get("object_type")
        assert result is not None, "Required property 'object_type' is missing"
        return result

    @builtins.property
    def object_namespace(self) -> typing.Optional[builtins.str]:
        """(experimental) The namespace the object belongs to.

        :default: 'default'

        :stability: experimental
        """
        result = self._values.get("object_namespace")
        return result

    @builtins.property
    def timeout(self) -> typing.Optional[aws_cdk.core.Duration]:
        """(experimental) Timeout for waiting on a value.

        :default: Duration.minutes(5)

        :stability: experimental
        """
        result = self._values.get("timeout")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "KubernetesObjectValueProps(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


class KubernetesPatch(
    aws_cdk.core.Construct,
    metaclass=jsii.JSIIMeta,
    jsii_type="@aws-cdk/aws-eks.KubernetesPatch",
):
    """(experimental) A CloudFormation resource which applies/restores a JSON patch into a Kubernetes resource.

    :see: https://kubernetes.io/docs/tasks/run-application/update-api-object-kubectl-patch/
    :stability: experimental
    """

    def __init__(
        self,
        scope: constructs.Construct,
        id: builtins.str,
        *,
        apply_patch: typing.Mapping[builtins.str, typing.Any],
        cluster: ICluster,
        resource_name: builtins.str,
        restore_patch: typing.Mapping[builtins.str, typing.Any],
        patch_type: typing.Optional["PatchType"] = None,
        resource_namespace: typing.Optional[builtins.str] = None,
    ) -> None:
        """
        :param scope: -
        :param id: -
        :param apply_patch: (experimental) The JSON object to pass to ``kubectl patch`` when the resource is created/updated.
        :param cluster: (experimental) The cluster to apply the patch to. [disable-awslint:ref-via-interface]
        :param resource_name: (experimental) The full name of the resource to patch (e.g. ``deployment/coredns``).
        :param restore_patch: (experimental) The JSON object to pass to ``kubectl patch`` when the resource is removed.
        :param patch_type: (experimental) The patch type to pass to ``kubectl patch``. The default type used by ``kubectl patch`` is "strategic". Default: PatchType.STRATEGIC
        :param resource_namespace: (experimental) The kubernetes API namespace. Default: "default"

        :stability: experimental
        """
        props = KubernetesPatchProps(
            apply_patch=apply_patch,
            cluster=cluster,
            resource_name=resource_name,
            restore_patch=restore_patch,
            patch_type=patch_type,
            resource_namespace=resource_namespace,
        )

        jsii.create(KubernetesPatch, self, [scope, id, props])


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.KubernetesPatchProps",
    jsii_struct_bases=[],
    name_mapping={
        "apply_patch": "applyPatch",
        "cluster": "cluster",
        "resource_name": "resourceName",
        "restore_patch": "restorePatch",
        "patch_type": "patchType",
        "resource_namespace": "resourceNamespace",
    },
)
class KubernetesPatchProps:
    def __init__(
        self,
        *,
        apply_patch: typing.Mapping[builtins.str, typing.Any],
        cluster: ICluster,
        resource_name: builtins.str,
        restore_patch: typing.Mapping[builtins.str, typing.Any],
        patch_type: typing.Optional["PatchType"] = None,
        resource_namespace: typing.Optional[builtins.str] = None,
    ) -> None:
        """(experimental) Properties for KubernetesPatch.

        :param apply_patch: (experimental) The JSON object to pass to ``kubectl patch`` when the resource is created/updated.
        :param cluster: (experimental) The cluster to apply the patch to. [disable-awslint:ref-via-interface]
        :param resource_name: (experimental) The full name of the resource to patch (e.g. ``deployment/coredns``).
        :param restore_patch: (experimental) The JSON object to pass to ``kubectl patch`` when the resource is removed.
        :param patch_type: (experimental) The patch type to pass to ``kubectl patch``. The default type used by ``kubectl patch`` is "strategic". Default: PatchType.STRATEGIC
        :param resource_namespace: (experimental) The kubernetes API namespace. Default: "default"

        :stability: experimental
        """
        self._values: typing.Dict[str, typing.Any] = {
            "apply_patch": apply_patch,
            "cluster": cluster,
            "resource_name": resource_name,
            "restore_patch": restore_patch,
        }
        if patch_type is not None:
            self._values["patch_type"] = patch_type
        if resource_namespace is not None:
            self._values["resource_namespace"] = resource_namespace

    @builtins.property
    def apply_patch(self) -> typing.Mapping[builtins.str, typing.Any]:
        """(experimental) The JSON object to pass to ``kubectl patch`` when the resource is created/updated.

        :stability: experimental
        """
        result = self._values.get("apply_patch")
        assert result is not None, "Required property 'apply_patch' is missing"
        return result

    @builtins.property
    def cluster(self) -> ICluster:
        """(experimental) The cluster to apply the patch to.

        [disable-awslint:ref-via-interface]

        :stability: experimental
        """
        result = self._values.get("cluster")
        assert result is not None, "Required property 'cluster' is missing"
        return result

    @builtins.property
    def resource_name(self) -> builtins.str:
        """(experimental) The full name of the resource to patch (e.g. ``deployment/coredns``).

        :stability: experimental
        """
        result = self._values.get("resource_name")
        assert result is not None, "Required property 'resource_name' is missing"
        return result

    @builtins.property
    def restore_patch(self) -> typing.Mapping[builtins.str, typing.Any]:
        """(experimental) The JSON object to pass to ``kubectl patch`` when the resource is removed.

        :stability: experimental
        """
        result = self._values.get("restore_patch")
        assert result is not None, "Required property 'restore_patch' is missing"
        return result

    @builtins.property
    def patch_type(self) -> typing.Optional["PatchType"]:
        """(experimental) The patch type to pass to ``kubectl patch``.

        The default type used by ``kubectl patch`` is "strategic".

        :default: PatchType.STRATEGIC

        :stability: experimental
        """
        result = self._values.get("patch_type")
        return result

    @builtins.property
    def resource_namespace(self) -> typing.Optional[builtins.str]:
        """(experimental) The kubernetes API namespace.

        :default: "default"

        :stability: experimental
        """
        result = self._values.get("resource_namespace")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "KubernetesPatchProps(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


class KubernetesVersion(
    metaclass=jsii.JSIIMeta,
    jsii_type="@aws-cdk/aws-eks.KubernetesVersion",
):
    """(experimental) Kubernetes cluster version.

    :stability: experimental
    """

    @jsii.member(jsii_name="of")
    @builtins.classmethod
    def of(cls, version: builtins.str) -> "KubernetesVersion":
        """(experimental) Custom cluster version.

        :param version: custom version number.

        :stability: experimental
        """
        return jsii.sinvoke(cls, "of", [version])

    @jsii.python.classproperty # type: ignore
    @jsii.member(jsii_name="V1_14")
    def V1_14(cls) -> "KubernetesVersion":
        """(experimental) Kubernetes version 1.14.

        :stability: experimental
        """
        return jsii.sget(cls, "V1_14")

    @jsii.python.classproperty # type: ignore
    @jsii.member(jsii_name="V1_15")
    def V1_15(cls) -> "KubernetesVersion":
        """(experimental) Kubernetes version 1.15.

        :stability: experimental
        """
        return jsii.sget(cls, "V1_15")

    @jsii.python.classproperty # type: ignore
    @jsii.member(jsii_name="V1_16")
    def V1_16(cls) -> "KubernetesVersion":
        """(experimental) Kubernetes version 1.16.

        :stability: experimental
        """
        return jsii.sget(cls, "V1_16")

    @jsii.python.classproperty # type: ignore
    @jsii.member(jsii_name="V1_17")
    def V1_17(cls) -> "KubernetesVersion":
        """(experimental) Kubernetes version 1.17.

        :stability: experimental
        """
        return jsii.sget(cls, "V1_17")

    @jsii.python.classproperty # type: ignore
    @jsii.member(jsii_name="V1_18")
    def V1_18(cls) -> "KubernetesVersion":
        """(experimental) Kubernetes version 1.18.

        :stability: experimental
        """
        return jsii.sget(cls, "V1_18")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="version")
    def version(self) -> builtins.str:
        """(experimental) cluster version number.

        :stability: experimental
        """
        return jsii.get(self, "version")


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.LaunchTemplateSpec",
    jsii_struct_bases=[],
    name_mapping={"id": "id", "version": "version"},
)
class LaunchTemplateSpec:
    def __init__(
        self,
        *,
        id: builtins.str,
        version: typing.Optional[builtins.str] = None,
    ) -> None:
        """(experimental) Launch template property specification.

        :param id: (experimental) The Launch template ID.
        :param version: (experimental) The launch template version to be used (optional). Default: - the default version of the launch template

        :stability: experimental
        """
        self._values: typing.Dict[str, typing.Any] = {
            "id": id,
        }
        if version is not None:
            self._values["version"] = version

    @builtins.property
    def id(self) -> builtins.str:
        """(experimental) The Launch template ID.

        :stability: experimental
        """
        result = self._values.get("id")
        assert result is not None, "Required property 'id' is missing"
        return result

    @builtins.property
    def version(self) -> typing.Optional[builtins.str]:
        """(experimental) The launch template version to be used (optional).

        :default: - the default version of the launch template

        :stability: experimental
        """
        result = self._values.get("version")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "LaunchTemplateSpec(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


@jsii.enum(jsii_type="@aws-cdk/aws-eks.MachineImageType")
class MachineImageType(enum.Enum):
    """(experimental) The machine image type.

    :stability: experimental
    """

    AMAZON_LINUX_2 = "AMAZON_LINUX_2"
    """(experimental) Amazon EKS-optimized Linux AMI.

    :stability: experimental
    """
    BOTTLEROCKET = "BOTTLEROCKET"
    """(experimental) Bottlerocket AMI.

    :stability: experimental
    """


@jsii.enum(jsii_type="@aws-cdk/aws-eks.NodeType")
class NodeType(enum.Enum):
    """(experimental) Whether the worker nodes should support GPU or just standard instances.

    :stability: experimental
    """

    STANDARD = "STANDARD"
    """(experimental) Standard instances.

    :stability: experimental
    """
    GPU = "GPU"
    """(experimental) GPU instances.

    :stability: experimental
    """
    INFERENTIA = "INFERENTIA"
    """(experimental) Inferentia instances.

    :stability: experimental
    """


@jsii.implements(INodegroup)
class Nodegroup(
    aws_cdk.core.Resource,
    metaclass=jsii.JSIIMeta,
    jsii_type="@aws-cdk/aws-eks.Nodegroup",
):
    """(experimental) The Nodegroup resource class.

    :stability: experimental
    """

    def __init__(
        self,
        scope: constructs.Construct,
        id: builtins.str,
        *,
        cluster: ICluster,
        ami_type: typing.Optional["NodegroupAmiType"] = None,
        desired_size: typing.Optional[jsii.Number] = None,
        disk_size: typing.Optional[jsii.Number] = None,
        force_update: typing.Optional[builtins.bool] = None,
        instance_type: typing.Optional[aws_cdk.aws_ec2.InstanceType] = None,
        labels: typing.Optional[typing.Mapping[builtins.str, builtins.str]] = None,
        launch_template_spec: typing.Optional[LaunchTemplateSpec] = None,
        max_size: typing.Optional[jsii.Number] = None,
        min_size: typing.Optional[jsii.Number] = None,
        nodegroup_name: typing.Optional[builtins.str] = None,
        node_role: typing.Optional[aws_cdk.aws_iam.IRole] = None,
        release_version: typing.Optional[builtins.str] = None,
        remote_access: typing.Optional["NodegroupRemoteAccess"] = None,
        subnets: typing.Optional[aws_cdk.aws_ec2.SubnetSelection] = None,
        tags: typing.Optional[typing.Mapping[builtins.str, builtins.str]] = None,
    ) -> None:
        """
        :param scope: -
        :param id: -
        :param cluster: (experimental) Cluster resource.
        :param ami_type: (experimental) The AMI type for your node group. Default: - auto-determined from the instanceType property.
        :param desired_size: (experimental) The current number of worker nodes that the managed node group should maintain. If not specified, the nodewgroup will initially create ``minSize`` instances. Default: 2
        :param disk_size: (experimental) The root device disk size (in GiB) for your node group instances. Default: 20
        :param force_update: (experimental) Force the update if the existing node group's pods are unable to be drained due to a pod disruption budget issue. If an update fails because pods could not be drained, you can force the update after it fails to terminate the old node whether or not any pods are running on the node. Default: true
        :param instance_type: (experimental) The instance type to use for your node group. Currently, you can specify a single instance type for a node group. The default value for this parameter is ``t3.medium``. If you choose a GPU instance type, be sure to specify the ``AL2_x86_64_GPU`` with the amiType parameter. Default: t3.medium
        :param labels: (experimental) The Kubernetes labels to be applied to the nodes in the node group when they are created. Default: - None
        :param launch_template_spec: (experimental) Launch template specification used for the nodegroup. Default: - no launch template
        :param max_size: (experimental) The maximum number of worker nodes that the managed node group can scale out to. Managed node groups can support up to 100 nodes by default. Default: - desiredSize
        :param min_size: (experimental) The minimum number of worker nodes that the managed node group can scale in to. This number must be greater than zero. Default: 1
        :param nodegroup_name: (experimental) Name of the Nodegroup. Default: - resource ID
        :param node_role: (experimental) The IAM role to associate with your node group. The Amazon EKS worker node kubelet daemon makes calls to AWS APIs on your behalf. Worker nodes receive permissions for these API calls through an IAM instance profile and associated policies. Before you can launch worker nodes and register them into a cluster, you must create an IAM role for those worker nodes to use when they are launched. Default: - None. Auto-generated if not specified.
        :param release_version: (experimental) The AMI version of the Amazon EKS-optimized AMI to use with your node group (for example, ``1.14.7-YYYYMMDD``). Default: - The latest available AMI version for the node group's current Kubernetes version is used.
        :param remote_access: (experimental) The remote access (SSH) configuration to use with your node group. Disabled by default, however, if you specify an Amazon EC2 SSH key but do not specify a source security group when you create a managed node group, then port 22 on the worker nodes is opened to the internet (0.0.0.0/0) Default: - disabled
        :param subnets: (experimental) The subnets to use for the Auto Scaling group that is created for your node group. By specifying the SubnetSelection, the selected subnets will automatically apply required tags i.e. ``kubernetes.io/cluster/CLUSTER_NAME`` with a value of ``shared``, where ``CLUSTER_NAME`` is replaced with the name of your cluster. Default: - private subnets
        :param tags: (experimental) The metadata to apply to the node group to assist with categorization and organization. Each tag consists of a key and an optional value, both of which you define. Node group tags do not propagate to any other resources associated with the node group, such as the Amazon EC2 instances or subnets. Default: - None

        :stability: experimental
        """
        props = NodegroupProps(
            cluster=cluster,
            ami_type=ami_type,
            desired_size=desired_size,
            disk_size=disk_size,
            force_update=force_update,
            instance_type=instance_type,
            labels=labels,
            launch_template_spec=launch_template_spec,
            max_size=max_size,
            min_size=min_size,
            nodegroup_name=nodegroup_name,
            node_role=node_role,
            release_version=release_version,
            remote_access=remote_access,
            subnets=subnets,
            tags=tags,
        )

        jsii.create(Nodegroup, self, [scope, id, props])

    @jsii.member(jsii_name="fromNodegroupName")
    @builtins.classmethod
    def from_nodegroup_name(
        cls,
        scope: constructs.Construct,
        id: builtins.str,
        nodegroup_name: builtins.str,
    ) -> INodegroup:
        """(experimental) Import the Nodegroup from attributes.

        :param scope: -
        :param id: -
        :param nodegroup_name: -

        :stability: experimental
        """
        return jsii.sinvoke(cls, "fromNodegroupName", [scope, id, nodegroup_name])

    @builtins.property # type: ignore
    @jsii.member(jsii_name="cluster")
    def cluster(self) -> ICluster:
        """(experimental) the Amazon EKS cluster resource.

        :stability: experimental
        :attribute: ClusterName
        """
        return jsii.get(self, "cluster")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="nodegroupArn")
    def nodegroup_arn(self) -> builtins.str:
        """(experimental) ARN of the nodegroup.

        :stability: experimental
        :attribute: true
        """
        return jsii.get(self, "nodegroupArn")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="nodegroupName")
    def nodegroup_name(self) -> builtins.str:
        """(experimental) Nodegroup name.

        :stability: experimental
        :attribute: true
        """
        return jsii.get(self, "nodegroupName")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="role")
    def role(self) -> aws_cdk.aws_iam.IRole:
        """(experimental) IAM role of the instance profile for the nodegroup.

        :stability: experimental
        """
        return jsii.get(self, "role")


@jsii.enum(jsii_type="@aws-cdk/aws-eks.NodegroupAmiType")
class NodegroupAmiType(enum.Enum):
    """(experimental) The AMI type for your node group.

    GPU instance types should use the ``AL2_x86_64_GPU`` AMI type, which uses the
    Amazon EKS-optimized Linux AMI with GPU support. Non-GPU instances should use the ``AL2_x86_64`` AMI type, which
    uses the Amazon EKS-optimized Linux AMI.

    :stability: experimental
    """

    AL2_X86_64 = "AL2_X86_64"
    """(experimental) Amazon Linux 2 (x86-64).

    :stability: experimental
    """
    AL2_X86_64_GPU = "AL2_X86_64_GPU"
    """(experimental) Amazon Linux 2 with GPU support.

    :stability: experimental
    """
    AL2_ARM_64 = "AL2_ARM_64"
    """(experimental) Amazon Linux 2 (ARM-64).

    :stability: experimental
    """


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.NodegroupOptions",
    jsii_struct_bases=[],
    name_mapping={
        "ami_type": "amiType",
        "desired_size": "desiredSize",
        "disk_size": "diskSize",
        "force_update": "forceUpdate",
        "instance_type": "instanceType",
        "labels": "labels",
        "launch_template_spec": "launchTemplateSpec",
        "max_size": "maxSize",
        "min_size": "minSize",
        "nodegroup_name": "nodegroupName",
        "node_role": "nodeRole",
        "release_version": "releaseVersion",
        "remote_access": "remoteAccess",
        "subnets": "subnets",
        "tags": "tags",
    },
)
class NodegroupOptions:
    def __init__(
        self,
        *,
        ami_type: typing.Optional[NodegroupAmiType] = None,
        desired_size: typing.Optional[jsii.Number] = None,
        disk_size: typing.Optional[jsii.Number] = None,
        force_update: typing.Optional[builtins.bool] = None,
        instance_type: typing.Optional[aws_cdk.aws_ec2.InstanceType] = None,
        labels: typing.Optional[typing.Mapping[builtins.str, builtins.str]] = None,
        launch_template_spec: typing.Optional[LaunchTemplateSpec] = None,
        max_size: typing.Optional[jsii.Number] = None,
        min_size: typing.Optional[jsii.Number] = None,
        nodegroup_name: typing.Optional[builtins.str] = None,
        node_role: typing.Optional[aws_cdk.aws_iam.IRole] = None,
        release_version: typing.Optional[builtins.str] = None,
        remote_access: typing.Optional["NodegroupRemoteAccess"] = None,
        subnets: typing.Optional[aws_cdk.aws_ec2.SubnetSelection] = None,
        tags: typing.Optional[typing.Mapping[builtins.str, builtins.str]] = None,
    ) -> None:
        """(experimental) The Nodegroup Options for addNodeGroup() method.

        :param ami_type: (experimental) The AMI type for your node group. Default: - auto-determined from the instanceType property.
        :param desired_size: (experimental) The current number of worker nodes that the managed node group should maintain. If not specified, the nodewgroup will initially create ``minSize`` instances. Default: 2
        :param disk_size: (experimental) The root device disk size (in GiB) for your node group instances. Default: 20
        :param force_update: (experimental) Force the update if the existing node group's pods are unable to be drained due to a pod disruption budget issue. If an update fails because pods could not be drained, you can force the update after it fails to terminate the old node whether or not any pods are running on the node. Default: true
        :param instance_type: (experimental) The instance type to use for your node group. Currently, you can specify a single instance type for a node group. The default value for this parameter is ``t3.medium``. If you choose a GPU instance type, be sure to specify the ``AL2_x86_64_GPU`` with the amiType parameter. Default: t3.medium
        :param labels: (experimental) The Kubernetes labels to be applied to the nodes in the node group when they are created. Default: - None
        :param launch_template_spec: (experimental) Launch template specification used for the nodegroup. Default: - no launch template
        :param max_size: (experimental) The maximum number of worker nodes that the managed node group can scale out to. Managed node groups can support up to 100 nodes by default. Default: - desiredSize
        :param min_size: (experimental) The minimum number of worker nodes that the managed node group can scale in to. This number must be greater than zero. Default: 1
        :param nodegroup_name: (experimental) Name of the Nodegroup. Default: - resource ID
        :param node_role: (experimental) The IAM role to associate with your node group. The Amazon EKS worker node kubelet daemon makes calls to AWS APIs on your behalf. Worker nodes receive permissions for these API calls through an IAM instance profile and associated policies. Before you can launch worker nodes and register them into a cluster, you must create an IAM role for those worker nodes to use when they are launched. Default: - None. Auto-generated if not specified.
        :param release_version: (experimental) The AMI version of the Amazon EKS-optimized AMI to use with your node group (for example, ``1.14.7-YYYYMMDD``). Default: - The latest available AMI version for the node group's current Kubernetes version is used.
        :param remote_access: (experimental) The remote access (SSH) configuration to use with your node group. Disabled by default, however, if you specify an Amazon EC2 SSH key but do not specify a source security group when you create a managed node group, then port 22 on the worker nodes is opened to the internet (0.0.0.0/0) Default: - disabled
        :param subnets: (experimental) The subnets to use for the Auto Scaling group that is created for your node group. By specifying the SubnetSelection, the selected subnets will automatically apply required tags i.e. ``kubernetes.io/cluster/CLUSTER_NAME`` with a value of ``shared``, where ``CLUSTER_NAME`` is replaced with the name of your cluster. Default: - private subnets
        :param tags: (experimental) The metadata to apply to the node group to assist with categorization and organization. Each tag consists of a key and an optional value, both of which you define. Node group tags do not propagate to any other resources associated with the node group, such as the Amazon EC2 instances or subnets. Default: - None

        :stability: experimental
        """
        if isinstance(launch_template_spec, dict):
            launch_template_spec = LaunchTemplateSpec(**launch_template_spec)
        if isinstance(remote_access, dict):
            remote_access = NodegroupRemoteAccess(**remote_access)
        if isinstance(subnets, dict):
            subnets = aws_cdk.aws_ec2.SubnetSelection(**subnets)
        self._values: typing.Dict[str, typing.Any] = {}
        if ami_type is not None:
            self._values["ami_type"] = ami_type
        if desired_size is not None:
            self._values["desired_size"] = desired_size
        if disk_size is not None:
            self._values["disk_size"] = disk_size
        if force_update is not None:
            self._values["force_update"] = force_update
        if instance_type is not None:
            self._values["instance_type"] = instance_type
        if labels is not None:
            self._values["labels"] = labels
        if launch_template_spec is not None:
            self._values["launch_template_spec"] = launch_template_spec
        if max_size is not None:
            self._values["max_size"] = max_size
        if min_size is not None:
            self._values["min_size"] = min_size
        if nodegroup_name is not None:
            self._values["nodegroup_name"] = nodegroup_name
        if node_role is not None:
            self._values["node_role"] = node_role
        if release_version is not None:
            self._values["release_version"] = release_version
        if remote_access is not None:
            self._values["remote_access"] = remote_access
        if subnets is not None:
            self._values["subnets"] = subnets
        if tags is not None:
            self._values["tags"] = tags

    @builtins.property
    def ami_type(self) -> typing.Optional[NodegroupAmiType]:
        """(experimental) The AMI type for your node group.

        :default: - auto-determined from the instanceType property.

        :stability: experimental
        """
        result = self._values.get("ami_type")
        return result

    @builtins.property
    def desired_size(self) -> typing.Optional[jsii.Number]:
        """(experimental) The current number of worker nodes that the managed node group should maintain.

        If not specified,
        the nodewgroup will initially create ``minSize`` instances.

        :default: 2

        :stability: experimental
        """
        result = self._values.get("desired_size")
        return result

    @builtins.property
    def disk_size(self) -> typing.Optional[jsii.Number]:
        """(experimental) The root device disk size (in GiB) for your node group instances.

        :default: 20

        :stability: experimental
        """
        result = self._values.get("disk_size")
        return result

    @builtins.property
    def force_update(self) -> typing.Optional[builtins.bool]:
        """(experimental) Force the update if the existing node group's pods are unable to be drained due to a pod disruption budget issue.

        If an update fails because pods could not be drained, you can force the update after it fails to terminate the old
        node whether or not any pods are
        running on the node.

        :default: true

        :stability: experimental
        """
        result = self._values.get("force_update")
        return result

    @builtins.property
    def instance_type(self) -> typing.Optional[aws_cdk.aws_ec2.InstanceType]:
        """(experimental) The instance type to use for your node group.

        Currently, you can specify a single instance type for a node group.
        The default value for this parameter is ``t3.medium``. If you choose a GPU instance type, be sure to specify the
        ``AL2_x86_64_GPU`` with the amiType parameter.

        :default: t3.medium

        :stability: experimental
        """
        result = self._values.get("instance_type")
        return result

    @builtins.property
    def labels(self) -> typing.Optional[typing.Mapping[builtins.str, builtins.str]]:
        """(experimental) The Kubernetes labels to be applied to the nodes in the node group when they are created.

        :default: - None

        :stability: experimental
        """
        result = self._values.get("labels")
        return result

    @builtins.property
    def launch_template_spec(self) -> typing.Optional[LaunchTemplateSpec]:
        """(experimental) Launch template specification used for the nodegroup.

        :default: - no launch template

        :see: - https://docs.aws.amazon.com/eks/latest/userguide/launch-templates.html
        :stability: experimental
        """
        result = self._values.get("launch_template_spec")
        return result

    @builtins.property
    def max_size(self) -> typing.Optional[jsii.Number]:
        """(experimental) The maximum number of worker nodes that the managed node group can scale out to.

        Managed node groups can support up to 100 nodes by default.

        :default: - desiredSize

        :stability: experimental
        """
        result = self._values.get("max_size")
        return result

    @builtins.property
    def min_size(self) -> typing.Optional[jsii.Number]:
        """(experimental) The minimum number of worker nodes that the managed node group can scale in to.

        This number must be greater than zero.

        :default: 1

        :stability: experimental
        """
        result = self._values.get("min_size")
        return result

    @builtins.property
    def nodegroup_name(self) -> typing.Optional[builtins.str]:
        """(experimental) Name of the Nodegroup.

        :default: - resource ID

        :stability: experimental
        """
        result = self._values.get("nodegroup_name")
        return result

    @builtins.property
    def node_role(self) -> typing.Optional[aws_cdk.aws_iam.IRole]:
        """(experimental) The IAM role to associate with your node group.

        The Amazon EKS worker node kubelet daemon
        makes calls to AWS APIs on your behalf. Worker nodes receive permissions for these API calls through
        an IAM instance profile and associated policies. Before you can launch worker nodes and register them
        into a cluster, you must create an IAM role for those worker nodes to use when they are launched.

        :default: - None. Auto-generated if not specified.

        :stability: experimental
        """
        result = self._values.get("node_role")
        return result

    @builtins.property
    def release_version(self) -> typing.Optional[builtins.str]:
        """(experimental) The AMI version of the Amazon EKS-optimized AMI to use with your node group (for example, ``1.14.7-YYYYMMDD``).

        :default: - The latest available AMI version for the node group's current Kubernetes version is used.

        :stability: experimental
        """
        result = self._values.get("release_version")
        return result

    @builtins.property
    def remote_access(self) -> typing.Optional["NodegroupRemoteAccess"]:
        """(experimental) The remote access (SSH) configuration to use with your node group.

        Disabled by default, however, if you
        specify an Amazon EC2 SSH key but do not specify a source security group when you create a managed node group,
        then port 22 on the worker nodes is opened to the internet (0.0.0.0/0)

        :default: - disabled

        :stability: experimental
        """
        result = self._values.get("remote_access")
        return result

    @builtins.property
    def subnets(self) -> typing.Optional[aws_cdk.aws_ec2.SubnetSelection]:
        """(experimental) The subnets to use for the Auto Scaling group that is created for your node group.

        By specifying the
        SubnetSelection, the selected subnets will automatically apply required tags i.e.
        ``kubernetes.io/cluster/CLUSTER_NAME`` with a value of ``shared``, where ``CLUSTER_NAME`` is replaced with
        the name of your cluster.

        :default: - private subnets

        :stability: experimental
        """
        result = self._values.get("subnets")
        return result

    @builtins.property
    def tags(self) -> typing.Optional[typing.Mapping[builtins.str, builtins.str]]:
        """(experimental) The metadata to apply to the node group to assist with categorization and organization.

        Each tag consists of
        a key and an optional value, both of which you define. Node group tags do not propagate to any other resources
        associated with the node group, such as the Amazon EC2 instances or subnets.

        :default: - None

        :stability: experimental
        """
        result = self._values.get("tags")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "NodegroupOptions(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.NodegroupProps",
    jsii_struct_bases=[NodegroupOptions],
    name_mapping={
        "ami_type": "amiType",
        "desired_size": "desiredSize",
        "disk_size": "diskSize",
        "force_update": "forceUpdate",
        "instance_type": "instanceType",
        "labels": "labels",
        "launch_template_spec": "launchTemplateSpec",
        "max_size": "maxSize",
        "min_size": "minSize",
        "nodegroup_name": "nodegroupName",
        "node_role": "nodeRole",
        "release_version": "releaseVersion",
        "remote_access": "remoteAccess",
        "subnets": "subnets",
        "tags": "tags",
        "cluster": "cluster",
    },
)
class NodegroupProps(NodegroupOptions):
    def __init__(
        self,
        *,
        ami_type: typing.Optional[NodegroupAmiType] = None,
        desired_size: typing.Optional[jsii.Number] = None,
        disk_size: typing.Optional[jsii.Number] = None,
        force_update: typing.Optional[builtins.bool] = None,
        instance_type: typing.Optional[aws_cdk.aws_ec2.InstanceType] = None,
        labels: typing.Optional[typing.Mapping[builtins.str, builtins.str]] = None,
        launch_template_spec: typing.Optional[LaunchTemplateSpec] = None,
        max_size: typing.Optional[jsii.Number] = None,
        min_size: typing.Optional[jsii.Number] = None,
        nodegroup_name: typing.Optional[builtins.str] = None,
        node_role: typing.Optional[aws_cdk.aws_iam.IRole] = None,
        release_version: typing.Optional[builtins.str] = None,
        remote_access: typing.Optional["NodegroupRemoteAccess"] = None,
        subnets: typing.Optional[aws_cdk.aws_ec2.SubnetSelection] = None,
        tags: typing.Optional[typing.Mapping[builtins.str, builtins.str]] = None,
        cluster: ICluster,
    ) -> None:
        """(experimental) NodeGroup properties interface.

        :param ami_type: (experimental) The AMI type for your node group. Default: - auto-determined from the instanceType property.
        :param desired_size: (experimental) The current number of worker nodes that the managed node group should maintain. If not specified, the nodewgroup will initially create ``minSize`` instances. Default: 2
        :param disk_size: (experimental) The root device disk size (in GiB) for your node group instances. Default: 20
        :param force_update: (experimental) Force the update if the existing node group's pods are unable to be drained due to a pod disruption budget issue. If an update fails because pods could not be drained, you can force the update after it fails to terminate the old node whether or not any pods are running on the node. Default: true
        :param instance_type: (experimental) The instance type to use for your node group. Currently, you can specify a single instance type for a node group. The default value for this parameter is ``t3.medium``. If you choose a GPU instance type, be sure to specify the ``AL2_x86_64_GPU`` with the amiType parameter. Default: t3.medium
        :param labels: (experimental) The Kubernetes labels to be applied to the nodes in the node group when they are created. Default: - None
        :param launch_template_spec: (experimental) Launch template specification used for the nodegroup. Default: - no launch template
        :param max_size: (experimental) The maximum number of worker nodes that the managed node group can scale out to. Managed node groups can support up to 100 nodes by default. Default: - desiredSize
        :param min_size: (experimental) The minimum number of worker nodes that the managed node group can scale in to. This number must be greater than zero. Default: 1
        :param nodegroup_name: (experimental) Name of the Nodegroup. Default: - resource ID
        :param node_role: (experimental) The IAM role to associate with your node group. The Amazon EKS worker node kubelet daemon makes calls to AWS APIs on your behalf. Worker nodes receive permissions for these API calls through an IAM instance profile and associated policies. Before you can launch worker nodes and register them into a cluster, you must create an IAM role for those worker nodes to use when they are launched. Default: - None. Auto-generated if not specified.
        :param release_version: (experimental) The AMI version of the Amazon EKS-optimized AMI to use with your node group (for example, ``1.14.7-YYYYMMDD``). Default: - The latest available AMI version for the node group's current Kubernetes version is used.
        :param remote_access: (experimental) The remote access (SSH) configuration to use with your node group. Disabled by default, however, if you specify an Amazon EC2 SSH key but do not specify a source security group when you create a managed node group, then port 22 on the worker nodes is opened to the internet (0.0.0.0/0) Default: - disabled
        :param subnets: (experimental) The subnets to use for the Auto Scaling group that is created for your node group. By specifying the SubnetSelection, the selected subnets will automatically apply required tags i.e. ``kubernetes.io/cluster/CLUSTER_NAME`` with a value of ``shared``, where ``CLUSTER_NAME`` is replaced with the name of your cluster. Default: - private subnets
        :param tags: (experimental) The metadata to apply to the node group to assist with categorization and organization. Each tag consists of a key and an optional value, both of which you define. Node group tags do not propagate to any other resources associated with the node group, such as the Amazon EC2 instances or subnets. Default: - None
        :param cluster: (experimental) Cluster resource.

        :stability: experimental
        """
        if isinstance(launch_template_spec, dict):
            launch_template_spec = LaunchTemplateSpec(**launch_template_spec)
        if isinstance(remote_access, dict):
            remote_access = NodegroupRemoteAccess(**remote_access)
        if isinstance(subnets, dict):
            subnets = aws_cdk.aws_ec2.SubnetSelection(**subnets)
        self._values: typing.Dict[str, typing.Any] = {
            "cluster": cluster,
        }
        if ami_type is not None:
            self._values["ami_type"] = ami_type
        if desired_size is not None:
            self._values["desired_size"] = desired_size
        if disk_size is not None:
            self._values["disk_size"] = disk_size
        if force_update is not None:
            self._values["force_update"] = force_update
        if instance_type is not None:
            self._values["instance_type"] = instance_type
        if labels is not None:
            self._values["labels"] = labels
        if launch_template_spec is not None:
            self._values["launch_template_spec"] = launch_template_spec
        if max_size is not None:
            self._values["max_size"] = max_size
        if min_size is not None:
            self._values["min_size"] = min_size
        if nodegroup_name is not None:
            self._values["nodegroup_name"] = nodegroup_name
        if node_role is not None:
            self._values["node_role"] = node_role
        if release_version is not None:
            self._values["release_version"] = release_version
        if remote_access is not None:
            self._values["remote_access"] = remote_access
        if subnets is not None:
            self._values["subnets"] = subnets
        if tags is not None:
            self._values["tags"] = tags

    @builtins.property
    def ami_type(self) -> typing.Optional[NodegroupAmiType]:
        """(experimental) The AMI type for your node group.

        :default: - auto-determined from the instanceType property.

        :stability: experimental
        """
        result = self._values.get("ami_type")
        return result

    @builtins.property
    def desired_size(self) -> typing.Optional[jsii.Number]:
        """(experimental) The current number of worker nodes that the managed node group should maintain.

        If not specified,
        the nodewgroup will initially create ``minSize`` instances.

        :default: 2

        :stability: experimental
        """
        result = self._values.get("desired_size")
        return result

    @builtins.property
    def disk_size(self) -> typing.Optional[jsii.Number]:
        """(experimental) The root device disk size (in GiB) for your node group instances.

        :default: 20

        :stability: experimental
        """
        result = self._values.get("disk_size")
        return result

    @builtins.property
    def force_update(self) -> typing.Optional[builtins.bool]:
        """(experimental) Force the update if the existing node group's pods are unable to be drained due to a pod disruption budget issue.

        If an update fails because pods could not be drained, you can force the update after it fails to terminate the old
        node whether or not any pods are
        running on the node.

        :default: true

        :stability: experimental
        """
        result = self._values.get("force_update")
        return result

    @builtins.property
    def instance_type(self) -> typing.Optional[aws_cdk.aws_ec2.InstanceType]:
        """(experimental) The instance type to use for your node group.

        Currently, you can specify a single instance type for a node group.
        The default value for this parameter is ``t3.medium``. If you choose a GPU instance type, be sure to specify the
        ``AL2_x86_64_GPU`` with the amiType parameter.

        :default: t3.medium

        :stability: experimental
        """
        result = self._values.get("instance_type")
        return result

    @builtins.property
    def labels(self) -> typing.Optional[typing.Mapping[builtins.str, builtins.str]]:
        """(experimental) The Kubernetes labels to be applied to the nodes in the node group when they are created.

        :default: - None

        :stability: experimental
        """
        result = self._values.get("labels")
        return result

    @builtins.property
    def launch_template_spec(self) -> typing.Optional[LaunchTemplateSpec]:
        """(experimental) Launch template specification used for the nodegroup.

        :default: - no launch template

        :see: - https://docs.aws.amazon.com/eks/latest/userguide/launch-templates.html
        :stability: experimental
        """
        result = self._values.get("launch_template_spec")
        return result

    @builtins.property
    def max_size(self) -> typing.Optional[jsii.Number]:
        """(experimental) The maximum number of worker nodes that the managed node group can scale out to.

        Managed node groups can support up to 100 nodes by default.

        :default: - desiredSize

        :stability: experimental
        """
        result = self._values.get("max_size")
        return result

    @builtins.property
    def min_size(self) -> typing.Optional[jsii.Number]:
        """(experimental) The minimum number of worker nodes that the managed node group can scale in to.

        This number must be greater than zero.

        :default: 1

        :stability: experimental
        """
        result = self._values.get("min_size")
        return result

    @builtins.property
    def nodegroup_name(self) -> typing.Optional[builtins.str]:
        """(experimental) Name of the Nodegroup.

        :default: - resource ID

        :stability: experimental
        """
        result = self._values.get("nodegroup_name")
        return result

    @builtins.property
    def node_role(self) -> typing.Optional[aws_cdk.aws_iam.IRole]:
        """(experimental) The IAM role to associate with your node group.

        The Amazon EKS worker node kubelet daemon
        makes calls to AWS APIs on your behalf. Worker nodes receive permissions for these API calls through
        an IAM instance profile and associated policies. Before you can launch worker nodes and register them
        into a cluster, you must create an IAM role for those worker nodes to use when they are launched.

        :default: - None. Auto-generated if not specified.

        :stability: experimental
        """
        result = self._values.get("node_role")
        return result

    @builtins.property
    def release_version(self) -> typing.Optional[builtins.str]:
        """(experimental) The AMI version of the Amazon EKS-optimized AMI to use with your node group (for example, ``1.14.7-YYYYMMDD``).

        :default: - The latest available AMI version for the node group's current Kubernetes version is used.

        :stability: experimental
        """
        result = self._values.get("release_version")
        return result

    @builtins.property
    def remote_access(self) -> typing.Optional["NodegroupRemoteAccess"]:
        """(experimental) The remote access (SSH) configuration to use with your node group.

        Disabled by default, however, if you
        specify an Amazon EC2 SSH key but do not specify a source security group when you create a managed node group,
        then port 22 on the worker nodes is opened to the internet (0.0.0.0/0)

        :default: - disabled

        :stability: experimental
        """
        result = self._values.get("remote_access")
        return result

    @builtins.property
    def subnets(self) -> typing.Optional[aws_cdk.aws_ec2.SubnetSelection]:
        """(experimental) The subnets to use for the Auto Scaling group that is created for your node group.

        By specifying the
        SubnetSelection, the selected subnets will automatically apply required tags i.e.
        ``kubernetes.io/cluster/CLUSTER_NAME`` with a value of ``shared``, where ``CLUSTER_NAME`` is replaced with
        the name of your cluster.

        :default: - private subnets

        :stability: experimental
        """
        result = self._values.get("subnets")
        return result

    @builtins.property
    def tags(self) -> typing.Optional[typing.Mapping[builtins.str, builtins.str]]:
        """(experimental) The metadata to apply to the node group to assist with categorization and organization.

        Each tag consists of
        a key and an optional value, both of which you define. Node group tags do not propagate to any other resources
        associated with the node group, such as the Amazon EC2 instances or subnets.

        :default: - None

        :stability: experimental
        """
        result = self._values.get("tags")
        return result

    @builtins.property
    def cluster(self) -> ICluster:
        """(experimental) Cluster resource.

        :stability: experimental
        """
        result = self._values.get("cluster")
        assert result is not None, "Required property 'cluster' is missing"
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "NodegroupProps(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.NodegroupRemoteAccess",
    jsii_struct_bases=[],
    name_mapping={
        "ssh_key_name": "sshKeyName",
        "source_security_groups": "sourceSecurityGroups",
    },
)
class NodegroupRemoteAccess:
    def __init__(
        self,
        *,
        ssh_key_name: builtins.str,
        source_security_groups: typing.Optional[typing.List[aws_cdk.aws_ec2.ISecurityGroup]] = None,
    ) -> None:
        """(experimental) The remote access (SSH) configuration to use with your node group.

        :param ssh_key_name: (experimental) The Amazon EC2 SSH key that provides access for SSH communication with the worker nodes in the managed node group.
        :param source_security_groups: (experimental) The security groups that are allowed SSH access (port 22) to the worker nodes. If you specify an Amazon EC2 SSH key but do not specify a source security group when you create a managed node group, then port 22 on the worker nodes is opened to the internet (0.0.0.0/0). Default: - port 22 on the worker nodes is opened to the internet (0.0.0.0/0)

        :see: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-nodegroup-remoteaccess.html
        :stability: experimental
        """
        self._values: typing.Dict[str, typing.Any] = {
            "ssh_key_name": ssh_key_name,
        }
        if source_security_groups is not None:
            self._values["source_security_groups"] = source_security_groups

    @builtins.property
    def ssh_key_name(self) -> builtins.str:
        """(experimental) The Amazon EC2 SSH key that provides access for SSH communication with the worker nodes in the managed node group.

        :stability: experimental
        """
        result = self._values.get("ssh_key_name")
        assert result is not None, "Required property 'ssh_key_name' is missing"
        return result

    @builtins.property
    def source_security_groups(
        self,
    ) -> typing.Optional[typing.List[aws_cdk.aws_ec2.ISecurityGroup]]:
        """(experimental) The security groups that are allowed SSH access (port 22) to the worker nodes.

        If you specify an Amazon EC2 SSH
        key but do not specify a source security group when you create a managed node group, then port 22 on the worker
        nodes is opened to the internet (0.0.0.0/0).

        :default: - port 22 on the worker nodes is opened to the internet (0.0.0.0/0)

        :stability: experimental
        """
        result = self._values.get("source_security_groups")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "NodegroupRemoteAccess(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


class OpenIdConnectProvider(
    aws_cdk.aws_iam.OpenIdConnectProvider,
    metaclass=jsii.JSIIMeta,
    jsii_type="@aws-cdk/aws-eks.OpenIdConnectProvider",
):
    """(experimental) IAM OIDC identity providers are entities in IAM that describe an external identity provider (IdP) service that supports the OpenID Connect (OIDC) standard, such as Google or Salesforce.

    You use an IAM OIDC identity provider
    when you want to establish trust between an OIDC-compatible IdP and your AWS
    account.

    This implementation has default values for thumbprints and clientIds props
    that will be compatible with the eks cluster

    :see: https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_oidc.html
    :stability: experimental
    :resource: AWS::CloudFormation::CustomResource
    """

    def __init__(
        self,
        scope: constructs.Construct,
        id: builtins.str,
        *,
        url: builtins.str,
    ) -> None:
        """(experimental) Defines an OpenID Connect provider.

        :param scope: The definition scope.
        :param id: Construct ID.
        :param url: (experimental) The URL of the identity provider. The URL must begin with https:// and should correspond to the iss claim in the provider's OpenID Connect ID tokens. Per the OIDC standard, path components are allowed but query parameters are not. Typically the URL consists of only a hostname, like https://server.example.org or https://example.com. You can find your OIDC Issuer URL by: aws eks describe-cluster --name %cluster_name% --query "cluster.identity.oidc.issuer" --output text

        :stability: experimental
        """
        props = OpenIdConnectProviderProps(url=url)

        jsii.create(OpenIdConnectProvider, self, [scope, id, props])


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.OpenIdConnectProviderProps",
    jsii_struct_bases=[],
    name_mapping={"url": "url"},
)
class OpenIdConnectProviderProps:
    def __init__(self, *, url: builtins.str) -> None:
        """(experimental) Initialization properties for ``OpenIdConnectProvider``.

        :param url: (experimental) The URL of the identity provider. The URL must begin with https:// and should correspond to the iss claim in the provider's OpenID Connect ID tokens. Per the OIDC standard, path components are allowed but query parameters are not. Typically the URL consists of only a hostname, like https://server.example.org or https://example.com. You can find your OIDC Issuer URL by: aws eks describe-cluster --name %cluster_name% --query "cluster.identity.oidc.issuer" --output text

        :stability: experimental
        """
        self._values: typing.Dict[str, typing.Any] = {
            "url": url,
        }

    @builtins.property
    def url(self) -> builtins.str:
        """(experimental) The URL of the identity provider.

        The URL must begin with https:// and
        should correspond to the iss claim in the provider's OpenID Connect ID
        tokens. Per the OIDC standard, path components are allowed but query
        parameters are not. Typically the URL consists of only a hostname, like
        https://server.example.org or https://example.com.

        You can find your OIDC Issuer URL by:
        aws eks describe-cluster --name %cluster_name% --query "cluster.identity.oidc.issuer" --output text

        :stability: experimental
        """
        result = self._values.get("url")
        assert result is not None, "Required property 'url' is missing"
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "OpenIdConnectProviderProps(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


@jsii.enum(jsii_type="@aws-cdk/aws-eks.PatchType")
class PatchType(enum.Enum):
    """(experimental) Values for ``kubectl patch`` --type argument.

    :stability: experimental
    """

    JSON = "JSON"
    """(experimental) JSON Patch, RFC 6902.

    :stability: experimental
    """
    MERGE = "MERGE"
    """(experimental) JSON Merge patch.

    :stability: experimental
    """
    STRATEGIC = "STRATEGIC"
    """(experimental) Strategic merge patch.

    :stability: experimental
    """


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.Selector",
    jsii_struct_bases=[],
    name_mapping={"namespace": "namespace", "labels": "labels"},
)
class Selector:
    def __init__(
        self,
        *,
        namespace: builtins.str,
        labels: typing.Optional[typing.Mapping[builtins.str, builtins.str]] = None,
    ) -> None:
        """(experimental) Fargate profile selector.

        :param namespace: (experimental) The Kubernetes namespace that the selector should match. You must specify a namespace for a selector. The selector only matches pods that are created in this namespace, but you can create multiple selectors to target multiple namespaces.
        :param labels: (experimental) The Kubernetes labels that the selector should match. A pod must contain all of the labels that are specified in the selector for it to be considered a match. Default: - all pods within the namespace will be selected.

        :stability: experimental
        """
        self._values: typing.Dict[str, typing.Any] = {
            "namespace": namespace,
        }
        if labels is not None:
            self._values["labels"] = labels

    @builtins.property
    def namespace(self) -> builtins.str:
        """(experimental) The Kubernetes namespace that the selector should match.

        You must specify a namespace for a selector. The selector only matches pods
        that are created in this namespace, but you can create multiple selectors
        to target multiple namespaces.

        :stability: experimental
        """
        result = self._values.get("namespace")
        assert result is not None, "Required property 'namespace' is missing"
        return result

    @builtins.property
    def labels(self) -> typing.Optional[typing.Mapping[builtins.str, builtins.str]]:
        """(experimental) The Kubernetes labels that the selector should match.

        A pod must contain
        all of the labels that are specified in the selector for it to be
        considered a match.

        :default: - all pods within the namespace will be selected.

        :stability: experimental
        """
        result = self._values.get("labels")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "Selector(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


@jsii.implements(aws_cdk.aws_iam.IPrincipal)
class ServiceAccount(
    aws_cdk.core.Construct,
    metaclass=jsii.JSIIMeta,
    jsii_type="@aws-cdk/aws-eks.ServiceAccount",
):
    """(experimental) Service Account.

    :stability: experimental
    """

    def __init__(
        self,
        scope: constructs.Construct,
        id: builtins.str,
        *,
        cluster: ICluster,
        name: typing.Optional[builtins.str] = None,
        namespace: typing.Optional[builtins.str] = None,
    ) -> None:
        """
        :param scope: -
        :param id: -
        :param cluster: (experimental) The cluster to apply the patch to.
        :param name: (experimental) The name of the service account. Default: - If no name is given, it will use the id of the resource.
        :param namespace: (experimental) The namespace of the service account. Default: "default"

        :stability: experimental
        """
        props = ServiceAccountProps(cluster=cluster, name=name, namespace=namespace)

        jsii.create(ServiceAccount, self, [scope, id, props])

    @jsii.member(jsii_name="addToPolicy")
    def add_to_policy(
        self,
        statement: aws_cdk.aws_iam.PolicyStatement,
    ) -> builtins.bool:
        """(experimental) (deprecated) Add to the policy of this principal.

        :param statement: -

        :stability: experimental
        """
        return jsii.invoke(self, "addToPolicy", [statement])

    @jsii.member(jsii_name="addToPrincipalPolicy")
    def add_to_principal_policy(
        self,
        statement: aws_cdk.aws_iam.PolicyStatement,
    ) -> aws_cdk.aws_iam.AddToPrincipalPolicyResult:
        """(experimental) Add to the policy of this principal.

        :param statement: -

        :stability: experimental
        """
        return jsii.invoke(self, "addToPrincipalPolicy", [statement])

    @builtins.property # type: ignore
    @jsii.member(jsii_name="assumeRoleAction")
    def assume_role_action(self) -> builtins.str:
        """(experimental) When this Principal is used in an AssumeRole policy, the action to use.

        :stability: experimental
        """
        return jsii.get(self, "assumeRoleAction")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="grantPrincipal")
    def grant_principal(self) -> aws_cdk.aws_iam.IPrincipal:
        """(experimental) The principal to grant permissions to.

        :stability: experimental
        """
        return jsii.get(self, "grantPrincipal")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="policyFragment")
    def policy_fragment(self) -> aws_cdk.aws_iam.PrincipalPolicyFragment:
        """(experimental) Return the policy fragment that identifies this principal in a Policy.

        :stability: experimental
        """
        return jsii.get(self, "policyFragment")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="role")
    def role(self) -> aws_cdk.aws_iam.IRole:
        """(experimental) The role which is linked to the service account.

        :stability: experimental
        """
        return jsii.get(self, "role")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="serviceAccountName")
    def service_account_name(self) -> builtins.str:
        """(experimental) The name of the service account.

        :stability: experimental
        """
        return jsii.get(self, "serviceAccountName")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="serviceAccountNamespace")
    def service_account_namespace(self) -> builtins.str:
        """(experimental) The namespace where the service account is located in.

        :stability: experimental
        """
        return jsii.get(self, "serviceAccountNamespace")


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.ServiceAccountOptions",
    jsii_struct_bases=[],
    name_mapping={"name": "name", "namespace": "namespace"},
)
class ServiceAccountOptions:
    def __init__(
        self,
        *,
        name: typing.Optional[builtins.str] = None,
        namespace: typing.Optional[builtins.str] = None,
    ) -> None:
        """(experimental) Options for ``ServiceAccount``.

        :param name: (experimental) The name of the service account. Default: - If no name is given, it will use the id of the resource.
        :param namespace: (experimental) The namespace of the service account. Default: "default"

        :stability: experimental
        """
        self._values: typing.Dict[str, typing.Any] = {}
        if name is not None:
            self._values["name"] = name
        if namespace is not None:
            self._values["namespace"] = namespace

    @builtins.property
    def name(self) -> typing.Optional[builtins.str]:
        """(experimental) The name of the service account.

        :default: - If no name is given, it will use the id of the resource.

        :stability: experimental
        """
        result = self._values.get("name")
        return result

    @builtins.property
    def namespace(self) -> typing.Optional[builtins.str]:
        """(experimental) The namespace of the service account.

        :default: "default"

        :stability: experimental
        """
        result = self._values.get("namespace")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "ServiceAccountOptions(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.ServiceAccountProps",
    jsii_struct_bases=[ServiceAccountOptions],
    name_mapping={"name": "name", "namespace": "namespace", "cluster": "cluster"},
)
class ServiceAccountProps(ServiceAccountOptions):
    def __init__(
        self,
        *,
        name: typing.Optional[builtins.str] = None,
        namespace: typing.Optional[builtins.str] = None,
        cluster: ICluster,
    ) -> None:
        """(experimental) Properties for defining service accounts.

        :param name: (experimental) The name of the service account. Default: - If no name is given, it will use the id of the resource.
        :param namespace: (experimental) The namespace of the service account. Default: "default"
        :param cluster: (experimental) The cluster to apply the patch to.

        :stability: experimental
        """
        self._values: typing.Dict[str, typing.Any] = {
            "cluster": cluster,
        }
        if name is not None:
            self._values["name"] = name
        if namespace is not None:
            self._values["namespace"] = namespace

    @builtins.property
    def name(self) -> typing.Optional[builtins.str]:
        """(experimental) The name of the service account.

        :default: - If no name is given, it will use the id of the resource.

        :stability: experimental
        """
        result = self._values.get("name")
        return result

    @builtins.property
    def namespace(self) -> typing.Optional[builtins.str]:
        """(experimental) The namespace of the service account.

        :default: "default"

        :stability: experimental
        """
        result = self._values.get("namespace")
        return result

    @builtins.property
    def cluster(self) -> ICluster:
        """(experimental) The cluster to apply the patch to.

        :stability: experimental
        """
        result = self._values.get("cluster")
        assert result is not None, "Required property 'cluster' is missing"
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "ServiceAccountProps(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.ServiceLoadBalancerAddressOptions",
    jsii_struct_bases=[],
    name_mapping={"namespace": "namespace", "timeout": "timeout"},
)
class ServiceLoadBalancerAddressOptions:
    def __init__(
        self,
        *,
        namespace: typing.Optional[builtins.str] = None,
        timeout: typing.Optional[aws_cdk.core.Duration] = None,
    ) -> None:
        """(experimental) Options for fetching a ServiceLoadBalancerAddress.

        :param namespace: (experimental) The namespace the service belongs to. Default: 'default'
        :param timeout: (experimental) Timeout for waiting on the load balancer address. Default: Duration.minutes(5)

        :stability: experimental
        """
        self._values: typing.Dict[str, typing.Any] = {}
        if namespace is not None:
            self._values["namespace"] = namespace
        if timeout is not None:
            self._values["timeout"] = timeout

    @builtins.property
    def namespace(self) -> typing.Optional[builtins.str]:
        """(experimental) The namespace the service belongs to.

        :default: 'default'

        :stability: experimental
        """
        result = self._values.get("namespace")
        return result

    @builtins.property
    def timeout(self) -> typing.Optional[aws_cdk.core.Duration]:
        """(experimental) Timeout for waiting on the load balancer address.

        :default: Duration.minutes(5)

        :stability: experimental
        """
        result = self._values.get("timeout")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "ServiceLoadBalancerAddressOptions(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


@jsii.implements(ICluster)
class Cluster(
    aws_cdk.core.Resource,
    metaclass=jsii.JSIIMeta,
    jsii_type="@aws-cdk/aws-eks.Cluster",
):
    """(experimental) A Cluster represents a managed Kubernetes Service (EKS).

    This is a fully managed cluster of API Servers (control-plane)
    The user is still required to create the worker nodes.

    :stability: experimental
    """

    def __init__(
        self,
        scope: constructs.Construct,
        id: builtins.str,
        *,
        default_capacity: typing.Optional[jsii.Number] = None,
        default_capacity_instance: typing.Optional[aws_cdk.aws_ec2.InstanceType] = None,
        default_capacity_type: typing.Optional[DefaultCapacityType] = None,
        secrets_encryption_key: typing.Optional[aws_cdk.aws_kms.IKey] = None,
        cluster_handler_environment: typing.Optional[typing.Mapping[builtins.str, builtins.str]] = None,
        core_dns_compute_type: typing.Optional[CoreDnsComputeType] = None,
        endpoint_access: typing.Optional[EndpointAccess] = None,
        kubectl_environment: typing.Optional[typing.Mapping[builtins.str, builtins.str]] = None,
        kubectl_layer: typing.Optional[aws_cdk.aws_lambda.ILayerVersion] = None,
        kubectl_memory: typing.Optional[aws_cdk.core.Size] = None,
        masters_role: typing.Optional[aws_cdk.aws_iam.IRole] = None,
        output_masters_role_arn: typing.Optional[builtins.bool] = None,
        place_cluster_handler_in_vpc: typing.Optional[builtins.bool] = None,
        prune: typing.Optional[builtins.bool] = None,
        version: KubernetesVersion,
        cluster_name: typing.Optional[builtins.str] = None,
        output_cluster_name: typing.Optional[builtins.bool] = None,
        output_config_command: typing.Optional[builtins.bool] = None,
        role: typing.Optional[aws_cdk.aws_iam.IRole] = None,
        security_group: typing.Optional[aws_cdk.aws_ec2.ISecurityGroup] = None,
        vpc: typing.Optional[aws_cdk.aws_ec2.IVpc] = None,
        vpc_subnets: typing.Optional[typing.List[aws_cdk.aws_ec2.SubnetSelection]] = None,
    ) -> None:
        """(experimental) Initiates an EKS Cluster with the supplied arguments.

        :param scope: a Construct, most likely a cdk.Stack created.
        :param id: the id of the Construct to create.
        :param default_capacity: (experimental) Number of instances to allocate as an initial capacity for this cluster. Instance type can be configured through ``defaultCapacityInstanceType``, which defaults to ``m5.large``. Use ``cluster.addAutoScalingGroupCapacity`` to add additional customized capacity. Set this to ``0`` is you wish to avoid the initial capacity allocation. Default: 2
        :param default_capacity_instance: (experimental) The instance type to use for the default capacity. This will only be taken into account if ``defaultCapacity`` is > 0. Default: m5.large
        :param default_capacity_type: (experimental) The default capacity type for the cluster. Default: NODEGROUP
        :param secrets_encryption_key: (experimental) KMS secret for envelope encryption for Kubernetes secrets. Default: - By default, Kubernetes stores all secret object data within etcd and all etcd volumes used by Amazon EKS are encrypted at the disk-level using AWS-Managed encryption keys.
        :param cluster_handler_environment: (experimental) Custom environment variables when interacting with the EKS endpoint to manage the cluster lifecycle. Default: - No environment variables.
        :param core_dns_compute_type: (experimental) Controls the "eks.amazonaws.com/compute-type" annotation in the CoreDNS configuration on your cluster to determine which compute type to use for CoreDNS. Default: CoreDnsComputeType.EC2 (for ``FargateCluster`` the default is FARGATE)
        :param endpoint_access: (experimental) Configure access to the Kubernetes API server endpoint.. Default: EndpointAccess.PUBLIC_AND_PRIVATE
        :param kubectl_environment: (experimental) Environment variables for the kubectl execution. Only relevant for kubectl enabled clusters. Default: - No environment variables.
        :param kubectl_layer: (experimental) An AWS Lambda Layer which includes ``kubectl``, Helm and the AWS CLI. By default, the provider will use the layer included in the "aws-lambda-layer-kubectl" SAR application which is available in all commercial regions. To deploy the layer locally, visit https://github.com/aws-samples/aws-lambda-layer-kubectl/blob/master/cdk/README.md for instructions on how to prepare the .zip file and then define it in your app as follows:: const layer = new lambda.LayerVersion(this, 'kubectl-layer', { code: lambda.Code.fromAsset(`${__dirname}/layer.zip`)), compatibleRuntimes: [lambda.Runtime.PROVIDED] }) Default: - the layer provided by the ``aws-lambda-layer-kubectl`` SAR app.
        :param kubectl_memory: (experimental) Amount of memory to allocate to the provider's lambda function. Default: Size.gibibytes(1)
        :param masters_role: (experimental) An IAM role that will be added to the ``system:masters`` Kubernetes RBAC group. Default: - a role that assumable by anyone with permissions in the same account will automatically be defined
        :param output_masters_role_arn: (experimental) Determines whether a CloudFormation output with the ARN of the "masters" IAM role will be synthesized (if ``mastersRole`` is specified). Default: false
        :param place_cluster_handler_in_vpc: (experimental) If set to true, the cluster handler functions will be placed in the private subnets of the cluster vpc, subject to the ``vpcSubnets`` selection strategy. Default: false
        :param prune: (experimental) Indicates whether Kubernetes resources added through ``addManifest()`` can be automatically pruned. When this is enabled (default), prune labels will be allocated and injected to each resource. These labels will then be used when issuing the ``kubectl apply`` operation with the ``--prune`` switch. Default: true
        :param version: (experimental) The Kubernetes version to run in the cluster.
        :param cluster_name: (experimental) Name for the cluster. Default: - Automatically generated name
        :param output_cluster_name: (experimental) Determines whether a CloudFormation output with the name of the cluster will be synthesized. Default: false
        :param output_config_command: (experimental) Determines whether a CloudFormation output with the ``aws eks update-kubeconfig`` command will be synthesized. This command will include the cluster name and, if applicable, the ARN of the masters IAM role. Default: true
        :param role: (experimental) Role that provides permissions for the Kubernetes control plane to make calls to AWS API operations on your behalf. Default: - A role is automatically created for you
        :param security_group: (experimental) Security Group to use for Control Plane ENIs. Default: - A security group is automatically created
        :param vpc: (experimental) The VPC in which to create the Cluster. Default: - a VPC with default configuration will be created and can be accessed through ``cluster.vpc``.
        :param vpc_subnets: (experimental) Where to place EKS Control Plane ENIs. If you want to create public load balancers, this must include public subnets. For example, to only select private subnets, supply the following:: vpcSubnets: [ { subnetType: ec2.SubnetType.Private } ] Default: - All public and private subnets

        :stability: experimental
        """
        props = ClusterProps(
            default_capacity=default_capacity,
            default_capacity_instance=default_capacity_instance,
            default_capacity_type=default_capacity_type,
            secrets_encryption_key=secrets_encryption_key,
            cluster_handler_environment=cluster_handler_environment,
            core_dns_compute_type=core_dns_compute_type,
            endpoint_access=endpoint_access,
            kubectl_environment=kubectl_environment,
            kubectl_layer=kubectl_layer,
            kubectl_memory=kubectl_memory,
            masters_role=masters_role,
            output_masters_role_arn=output_masters_role_arn,
            place_cluster_handler_in_vpc=place_cluster_handler_in_vpc,
            prune=prune,
            version=version,
            cluster_name=cluster_name,
            output_cluster_name=output_cluster_name,
            output_config_command=output_config_command,
            role=role,
            security_group=security_group,
            vpc=vpc,
            vpc_subnets=vpc_subnets,
        )

        jsii.create(Cluster, self, [scope, id, props])

    @jsii.member(jsii_name="fromClusterAttributes")
    @builtins.classmethod
    def from_cluster_attributes(
        cls,
        scope: constructs.Construct,
        id: builtins.str,
        *,
        cluster_name: builtins.str,
        cluster_certificate_authority_data: typing.Optional[builtins.str] = None,
        cluster_encryption_config_key_arn: typing.Optional[builtins.str] = None,
        cluster_endpoint: typing.Optional[builtins.str] = None,
        cluster_security_group_id: typing.Optional[builtins.str] = None,
        kubectl_environment: typing.Optional[typing.Mapping[builtins.str, builtins.str]] = None,
        kubectl_layer: typing.Optional[aws_cdk.aws_lambda.ILayerVersion] = None,
        kubectl_memory: typing.Optional[aws_cdk.core.Size] = None,
        kubectl_private_subnet_ids: typing.Optional[typing.List[builtins.str]] = None,
        kubectl_role_arn: typing.Optional[builtins.str] = None,
        kubectl_security_group_id: typing.Optional[builtins.str] = None,
        open_id_connect_provider: typing.Optional[aws_cdk.aws_iam.IOpenIdConnectProvider] = None,
        prune: typing.Optional[builtins.bool] = None,
        security_group_ids: typing.Optional[typing.List[builtins.str]] = None,
        vpc: typing.Optional[aws_cdk.aws_ec2.IVpc] = None,
    ) -> ICluster:
        """(experimental) Import an existing cluster.

        :param scope: the construct scope, in most cases 'this'.
        :param id: the id or name to import as.
        :param cluster_name: (experimental) The physical name of the Cluster.
        :param cluster_certificate_authority_data: (experimental) The certificate-authority-data for your cluster. Default: - if not specified ``cluster.clusterCertificateAuthorityData`` will throw an error
        :param cluster_encryption_config_key_arn: (experimental) Amazon Resource Name (ARN) or alias of the customer master key (CMK). Default: - if not specified ``cluster.clusterEncryptionConfigKeyArn`` will throw an error
        :param cluster_endpoint: (experimental) The API Server endpoint URL. Default: - if not specified ``cluster.clusterEndpoint`` will throw an error.
        :param cluster_security_group_id: (experimental) The cluster security group that was created by Amazon EKS for the cluster. Default: - if not specified ``cluster.clusterSecurityGroupId`` will throw an error
        :param kubectl_environment: (experimental) Environment variables to use when running ``kubectl`` against this cluster. Default: - no additional variables
        :param kubectl_layer: (experimental) An AWS Lambda Layer which includes ``kubectl``, Helm and the AWS CLI. By default, the provider will use the layer included in the "aws-lambda-layer-kubectl" SAR application which is available in all commercial regions. To deploy the layer locally, visit https://github.com/aws-samples/aws-lambda-layer-kubectl/blob/master/cdk/README.md for instructions on how to prepare the .zip file and then define it in your app as follows:: const layer = new lambda.LayerVersion(this, 'kubectl-layer', { code: lambda.Code.fromAsset(`${__dirname}/layer.zip`)), compatibleRuntimes: [lambda.Runtime.PROVIDED] }); Or you can use the standard layer like this (with options to customize the version and SAR application ID): ```ts const layer = new eks.KubectlLayer(this, 'KubectlLayer'); Default: - the layer provided by the ``aws-lambda-layer-kubectl`` SAR app.
        :param kubectl_memory: (experimental) Amount of memory to allocate to the provider's lambda function. Default: Size.gibibytes(1)
        :param kubectl_private_subnet_ids: (experimental) Subnets to host the ``kubectl`` compute resources. If not specified, the k8s endpoint is expected to be accessible publicly. Default: - k8s endpoint is expected to be accessible publicly
        :param kubectl_role_arn: (experimental) An IAM role with cluster administrator and "system:masters" permissions. Default: - if not specified, it not be possible to issue ``kubectl`` commands against an imported cluster.
        :param kubectl_security_group_id: (experimental) A security group to use for ``kubectl`` execution. If not specified, the k8s endpoint is expected to be accessible publicly. Default: - k8s endpoint is expected to be accessible publicly
        :param open_id_connect_provider: (experimental) An Open ID Connect provider for this cluster that can be used to configure service accounts. You can either import an existing provider using ``iam.OpenIdConnectProvider.fromProviderArn``, or create a new provider using ``new eks.OpenIdConnectProvider`` Default: - if not specified ``cluster.openIdConnectProvider`` and ``cluster.addServiceAccount`` will throw an error.
        :param prune: (experimental) Indicates whether Kubernetes resources added through ``addManifest()`` can be automatically pruned. When this is enabled (default), prune labels will be allocated and injected to each resource. These labels will then be used when issuing the ``kubectl apply`` operation with the ``--prune`` switch. Default: true
        :param security_group_ids: (experimental) Additional security groups associated with this cluster. Default: - if not specified, no additional security groups will be considered in ``cluster.connections``.
        :param vpc: (experimental) The VPC in which this Cluster was created. Default: - if not specified ``cluster.vpc`` will throw an error

        :stability: experimental
        """
        attrs = ClusterAttributes(
            cluster_name=cluster_name,
            cluster_certificate_authority_data=cluster_certificate_authority_data,
            cluster_encryption_config_key_arn=cluster_encryption_config_key_arn,
            cluster_endpoint=cluster_endpoint,
            cluster_security_group_id=cluster_security_group_id,
            kubectl_environment=kubectl_environment,
            kubectl_layer=kubectl_layer,
            kubectl_memory=kubectl_memory,
            kubectl_private_subnet_ids=kubectl_private_subnet_ids,
            kubectl_role_arn=kubectl_role_arn,
            kubectl_security_group_id=kubectl_security_group_id,
            open_id_connect_provider=open_id_connect_provider,
            prune=prune,
            security_group_ids=security_group_ids,
            vpc=vpc,
        )

        return jsii.sinvoke(cls, "fromClusterAttributes", [scope, id, attrs])

    @jsii.member(jsii_name="addAutoScalingGroupCapacity")
    def add_auto_scaling_group_capacity(
        self,
        id: builtins.str,
        *,
        instance_type: aws_cdk.aws_ec2.InstanceType,
        bootstrap_enabled: typing.Optional[builtins.bool] = None,
        bootstrap_options: typing.Optional[BootstrapOptions] = None,
        machine_image_type: typing.Optional[MachineImageType] = None,
        map_role: typing.Optional[builtins.bool] = None,
        allow_all_outbound: typing.Optional[builtins.bool] = None,
        associate_public_ip_address: typing.Optional[builtins.bool] = None,
        auto_scaling_group_name: typing.Optional[builtins.str] = None,
        block_devices: typing.Optional[typing.List[aws_cdk.aws_autoscaling.BlockDevice]] = None,
        cooldown: typing.Optional[aws_cdk.core.Duration] = None,
        desired_capacity: typing.Optional[jsii.Number] = None,
        group_metrics: typing.Optional[typing.List[aws_cdk.aws_autoscaling.GroupMetrics]] = None,
        health_check: typing.Optional[aws_cdk.aws_autoscaling.HealthCheck] = None,
        ignore_unmodified_size_properties: typing.Optional[builtins.bool] = None,
        instance_monitoring: typing.Optional[aws_cdk.aws_autoscaling.Monitoring] = None,
        key_name: typing.Optional[builtins.str] = None,
        max_capacity: typing.Optional[jsii.Number] = None,
        max_instance_lifetime: typing.Optional[aws_cdk.core.Duration] = None,
        min_capacity: typing.Optional[jsii.Number] = None,
        notifications: typing.Optional[typing.List[aws_cdk.aws_autoscaling.NotificationConfiguration]] = None,
        notifications_topic: typing.Optional[aws_cdk.aws_sns.ITopic] = None,
        replacing_update_min_successful_instances_percent: typing.Optional[jsii.Number] = None,
        resource_signal_count: typing.Optional[jsii.Number] = None,
        resource_signal_timeout: typing.Optional[aws_cdk.core.Duration] = None,
        rolling_update_configuration: typing.Optional[aws_cdk.aws_autoscaling.RollingUpdateConfiguration] = None,
        signals: typing.Optional[aws_cdk.aws_autoscaling.Signals] = None,
        spot_price: typing.Optional[builtins.str] = None,
        update_policy: typing.Optional[aws_cdk.aws_autoscaling.UpdatePolicy] = None,
        update_type: typing.Optional[aws_cdk.aws_autoscaling.UpdateType] = None,
        vpc_subnets: typing.Optional[aws_cdk.aws_ec2.SubnetSelection] = None,
    ) -> aws_cdk.aws_autoscaling.AutoScalingGroup:
        """(experimental) Add nodes to this EKS cluster.

        The nodes will automatically be configured with the right VPC and AMI
        for the instance type and Kubernetes version.

        Note that if you specify ``updateType: RollingUpdate`` or ``updateType: ReplacingUpdate``, your nodes might be replaced at deploy
        time without notice in case the recommended AMI for your machine image type has been updated by AWS.
        The default behavior for ``updateType`` is ``None``, which means only new instances will be launched using the new AMI.

        Spot instances will be labeled ``lifecycle=Ec2Spot`` and tainted with ``PreferNoSchedule``.
        In addition, the `spot interrupt handler <https://github.com/awslabs/ec2-spot-labs/tree/master/ec2-spot-eks-solution/spot-termination-handler>`_
        daemon will be installed on all spot instances to handle
        `EC2 Spot Instance Termination Notices <https://aws.amazon.com/blogs/aws/new-ec2-spot-instance-termination-notices/>`_.

        :param id: -
        :param instance_type: (experimental) Instance type of the instances to start.
        :param bootstrap_enabled: (experimental) Configures the EC2 user-data script for instances in this autoscaling group to bootstrap the node (invoke ``/etc/eks/bootstrap.sh``) and associate it with the EKS cluster. If you wish to provide a custom user data script, set this to ``false`` and manually invoke ``autoscalingGroup.addUserData()``. Default: true
        :param bootstrap_options: (experimental) EKS node bootstrapping options. Default: - none
        :param machine_image_type: (experimental) Machine image type. Default: MachineImageType.AMAZON_LINUX_2
        :param map_role: (experimental) Will automatically update the aws-auth ConfigMap to map the IAM instance role to RBAC. This cannot be explicitly set to ``true`` if the cluster has kubectl disabled. Default: - true if the cluster has kubectl enabled (which is the default).
        :param allow_all_outbound: Whether the instances can initiate connections to anywhere by default. Default: true
        :param associate_public_ip_address: Whether instances in the Auto Scaling Group should have public IP addresses associated with them. Default: - Use subnet setting.
        :param auto_scaling_group_name: The name of the Auto Scaling group. This name must be unique per Region per account. Default: - Auto generated by CloudFormation
        :param block_devices: Specifies how block devices are exposed to the instance. You can specify virtual devices and EBS volumes. Each instance that is launched has an associated root device volume, either an Amazon EBS volume or an instance store volume. You can use block device mappings to specify additional EBS volumes or instance store volumes to attach to an instance when it is launched. Default: - Uses the block device mapping of the AMI
        :param cooldown: Default scaling cooldown for this AutoScalingGroup. Default: Duration.minutes(5)
        :param desired_capacity: Initial amount of instances in the fleet. If this is set to a number, every deployment will reset the amount of instances to this number. It is recommended to leave this value blank. Default: minCapacity, and leave unchanged during deployment
        :param group_metrics: Enable monitoring for group metrics, these metrics describe the group rather than any of its instances. To report all group metrics use ``GroupMetrics.all()`` Group metrics are reported in a granularity of 1 minute at no additional charge. Default: - no group metrics will be reported
        :param health_check: Configuration for health checks. Default: - HealthCheck.ec2 with no grace period
        :param ignore_unmodified_size_properties: If the ASG has scheduled actions, don't reset unchanged group sizes. Only used if the ASG has scheduled actions (which may scale your ASG up or down regardless of cdk deployments). If true, the size of the group will only be reset if it has been changed in the CDK app. If false, the sizes will always be changed back to what they were in the CDK app on deployment. Default: true
        :param instance_monitoring: Controls whether instances in this group are launched with detailed or basic monitoring. When detailed monitoring is enabled, Amazon CloudWatch generates metrics every minute and your account is charged a fee. When you disable detailed monitoring, CloudWatch generates metrics every 5 minutes. Default: - Monitoring.DETAILED
        :param key_name: Name of SSH keypair to grant access to instances. Default: - No SSH access will be possible.
        :param max_capacity: Maximum number of instances in the fleet. Default: desiredCapacity
        :param max_instance_lifetime: The maximum amount of time that an instance can be in service. The maximum duration applies to all current and future instances in the group. As an instance approaches its maximum duration, it is terminated and replaced, and cannot be used again. You must specify a value of at least 604,800 seconds (7 days). To clear a previously set value, leave this property undefined. Default: none
        :param min_capacity: Minimum number of instances in the fleet. Default: 1
        :param notifications: Configure autoscaling group to send notifications about fleet changes to an SNS topic(s). Default: - No fleet change notifications will be sent.
        :param notifications_topic: (deprecated) SNS topic to send notifications about fleet changes. Default: - No fleet change notifications will be sent.
        :param replacing_update_min_successful_instances_percent: (deprecated) Configuration for replacing updates. Only used if updateType == UpdateType.ReplacingUpdate. Specifies how many instances must signal success for the update to succeed. Default: minSuccessfulInstancesPercent
        :param resource_signal_count: (deprecated) How many ResourceSignal calls CloudFormation expects before the resource is considered created. Default: 1 if resourceSignalTimeout is set, 0 otherwise
        :param resource_signal_timeout: (deprecated) The length of time to wait for the resourceSignalCount. The maximum value is 43200 (12 hours). Default: Duration.minutes(5) if resourceSignalCount is set, N/A otherwise
        :param rolling_update_configuration: (deprecated) Configuration for rolling updates. Only used if updateType == UpdateType.RollingUpdate. Default: - RollingUpdateConfiguration with defaults.
        :param signals: Configure waiting for signals during deployment. Use this to pause the CloudFormation deployment to wait for the instances in the AutoScalingGroup to report successful startup during creation and updates. The UserData script needs to invoke ``cfn-signal`` with a success or failure code after it is done setting up the instance. Without waiting for signals, the CloudFormation deployment will proceed as soon as the AutoScalingGroup has been created or updated but before the instances in the group have been started. For example, to have instances wait for an Elastic Load Balancing health check before they signal success, add a health-check verification by using the cfn-init helper script. For an example, see the verify_instance_health command in the Auto Scaling rolling updates sample template: https://github.com/awslabs/aws-cloudformation-templates/blob/master/aws/services/AutoScaling/AutoScalingRollingUpdates.yaml Default: - Do not wait for signals
        :param spot_price: The maximum hourly price (in USD) to be paid for any Spot Instance launched to fulfill the request. Spot Instances are launched when the price you specify exceeds the current Spot market price. Default: none
        :param update_policy: What to do when an AutoScalingGroup's instance configuration is changed. This is applied when any of the settings on the ASG are changed that affect how the instances should be created (VPC, instance type, startup scripts, etc.). It indicates how the existing instances should be replaced with new instances matching the new config. By default, nothing is done and only new instances are launched with the new config. Default: - ``UpdatePolicy.rollingUpdate()`` if using ``init``, ``UpdatePolicy.none()`` otherwise
        :param update_type: (deprecated) What to do when an AutoScalingGroup's instance configuration is changed. This is applied when any of the settings on the ASG are changed that affect how the instances should be created (VPC, instance type, startup scripts, etc.). It indicates how the existing instances should be replaced with new instances matching the new config. By default, nothing is done and only new instances are launched with the new config. Default: UpdateType.None
        :param vpc_subnets: Where to place instances within the VPC. Default: - All Private subnets.

        :stability: experimental
        """
        options = AutoScalingGroupCapacityOptions(
            instance_type=instance_type,
            bootstrap_enabled=bootstrap_enabled,
            bootstrap_options=bootstrap_options,
            machine_image_type=machine_image_type,
            map_role=map_role,
            allow_all_outbound=allow_all_outbound,
            associate_public_ip_address=associate_public_ip_address,
            auto_scaling_group_name=auto_scaling_group_name,
            block_devices=block_devices,
            cooldown=cooldown,
            desired_capacity=desired_capacity,
            group_metrics=group_metrics,
            health_check=health_check,
            ignore_unmodified_size_properties=ignore_unmodified_size_properties,
            instance_monitoring=instance_monitoring,
            key_name=key_name,
            max_capacity=max_capacity,
            max_instance_lifetime=max_instance_lifetime,
            min_capacity=min_capacity,
            notifications=notifications,
            notifications_topic=notifications_topic,
            replacing_update_min_successful_instances_percent=replacing_update_min_successful_instances_percent,
            resource_signal_count=resource_signal_count,
            resource_signal_timeout=resource_signal_timeout,
            rolling_update_configuration=rolling_update_configuration,
            signals=signals,
            spot_price=spot_price,
            update_policy=update_policy,
            update_type=update_type,
            vpc_subnets=vpc_subnets,
        )

        return jsii.invoke(self, "addAutoScalingGroupCapacity", [id, options])

    @jsii.member(jsii_name="addCdk8sChart")
    def add_cdk8s_chart(
        self,
        id: builtins.str,
        chart: constructs.Construct,
    ) -> KubernetesManifest:
        """(experimental) Defines a CDK8s chart in this cluster.

        :param id: logical id of this chart.
        :param chart: the cdk8s chart.

        :return: a ``KubernetesManifest`` construct representing the chart.

        :stability: experimental
        """
        return jsii.invoke(self, "addCdk8sChart", [id, chart])

    @jsii.member(jsii_name="addFargateProfile")
    def add_fargate_profile(
        self,
        id: builtins.str,
        *,
        selectors: typing.List[Selector],
        fargate_profile_name: typing.Optional[builtins.str] = None,
        pod_execution_role: typing.Optional[aws_cdk.aws_iam.IRole] = None,
        subnet_selection: typing.Optional[aws_cdk.aws_ec2.SubnetSelection] = None,
        vpc: typing.Optional[aws_cdk.aws_ec2.IVpc] = None,
    ) -> FargateProfile:
        """(experimental) Adds a Fargate profile to this cluster.

        :param id: the id of this profile.
        :param selectors: (experimental) The selectors to match for pods to use this Fargate profile. Each selector must have an associated namespace. Optionally, you can also specify labels for a namespace. At least one selector is required and you may specify up to five selectors.
        :param fargate_profile_name: (experimental) The name of the Fargate profile. Default: - generated
        :param pod_execution_role: (experimental) The pod execution role to use for pods that match the selectors in the Fargate profile. The pod execution role allows Fargate infrastructure to register with your cluster as a node, and it provides read access to Amazon ECR image repositories. Default: - a role will be automatically created
        :param subnet_selection: (experimental) Select which subnets to launch your pods into. At this time, pods running on Fargate are not assigned public IP addresses, so only private subnets (with no direct route to an Internet Gateway) are allowed. Default: - all private subnets of the VPC are selected.
        :param vpc: (experimental) The VPC from which to select subnets to launch your pods into. By default, all private subnets are selected. You can customize this using ``subnetSelection``. Default: - all private subnets used by theEKS cluster

        :see: https://docs.aws.amazon.com/eks/latest/userguide/fargate-profile.html
        :stability: experimental
        """
        options = FargateProfileOptions(
            selectors=selectors,
            fargate_profile_name=fargate_profile_name,
            pod_execution_role=pod_execution_role,
            subnet_selection=subnet_selection,
            vpc=vpc,
        )

        return jsii.invoke(self, "addFargateProfile", [id, options])

    @jsii.member(jsii_name="addHelmChart")
    def add_helm_chart(
        self,
        id: builtins.str,
        *,
        chart: builtins.str,
        create_namespace: typing.Optional[builtins.bool] = None,
        namespace: typing.Optional[builtins.str] = None,
        release: typing.Optional[builtins.str] = None,
        repository: typing.Optional[builtins.str] = None,
        timeout: typing.Optional[aws_cdk.core.Duration] = None,
        values: typing.Optional[typing.Mapping[builtins.str, typing.Any]] = None,
        version: typing.Optional[builtins.str] = None,
        wait: typing.Optional[builtins.bool] = None,
    ) -> HelmChart:
        """(experimental) Defines a Helm chart in this cluster.

        :param id: logical id of this chart.
        :param chart: (experimental) The name of the chart.
        :param create_namespace: (experimental) create namespace if not exist. Default: true
        :param namespace: (experimental) The Kubernetes namespace scope of the requests. Default: default
        :param release: (experimental) The name of the release. Default: - If no release name is given, it will use the last 53 characters of the node's unique id.
        :param repository: (experimental) The repository which contains the chart. For example: https://kubernetes-charts.storage.googleapis.com/ Default: - No repository will be used, which means that the chart needs to be an absolute URL.
        :param timeout: (experimental) Amount of time to wait for any individual Kubernetes operation. Maximum 15 minutes. Default: Duration.minutes(5)
        :param values: (experimental) The values to be used by the chart. Default: - No values are provided to the chart.
        :param version: (experimental) The chart version to install. Default: - If this is not specified, the latest version is installed
        :param wait: (experimental) Whether or not Helm should wait until all Pods, PVCs, Services, and minimum number of Pods of a Deployment, StatefulSet, or ReplicaSet are in a ready state before marking the release as successful. Default: - Helm will not wait before marking release as successful

        :return: a ``HelmChart`` construct

        :stability: experimental
        """
        options = HelmChartOptions(
            chart=chart,
            create_namespace=create_namespace,
            namespace=namespace,
            release=release,
            repository=repository,
            timeout=timeout,
            values=values,
            version=version,
            wait=wait,
        )

        return jsii.invoke(self, "addHelmChart", [id, options])

    @jsii.member(jsii_name="addManifest")
    def add_manifest(
        self,
        id: builtins.str,
        *manifest: typing.Mapping[builtins.str, typing.Any],
    ) -> KubernetesManifest:
        """(experimental) Defines a Kubernetes resource in this cluster.

        The manifest will be applied/deleted using kubectl as needed.

        :param id: logical id of this manifest.
        :param manifest: a list of Kubernetes resource specifications.

        :return: a ``KubernetesResource`` object.

        :stability: experimental
        """
        return jsii.invoke(self, "addManifest", [id, *manifest])

    @jsii.member(jsii_name="addNodegroupCapacity")
    def add_nodegroup_capacity(
        self,
        id: builtins.str,
        *,
        ami_type: typing.Optional[NodegroupAmiType] = None,
        desired_size: typing.Optional[jsii.Number] = None,
        disk_size: typing.Optional[jsii.Number] = None,
        force_update: typing.Optional[builtins.bool] = None,
        instance_type: typing.Optional[aws_cdk.aws_ec2.InstanceType] = None,
        labels: typing.Optional[typing.Mapping[builtins.str, builtins.str]] = None,
        launch_template_spec: typing.Optional[LaunchTemplateSpec] = None,
        max_size: typing.Optional[jsii.Number] = None,
        min_size: typing.Optional[jsii.Number] = None,
        nodegroup_name: typing.Optional[builtins.str] = None,
        node_role: typing.Optional[aws_cdk.aws_iam.IRole] = None,
        release_version: typing.Optional[builtins.str] = None,
        remote_access: typing.Optional[NodegroupRemoteAccess] = None,
        subnets: typing.Optional[aws_cdk.aws_ec2.SubnetSelection] = None,
        tags: typing.Optional[typing.Mapping[builtins.str, builtins.str]] = None,
    ) -> Nodegroup:
        """(experimental) Add managed nodegroup to this Amazon EKS cluster.

        This method will create a new managed nodegroup and add into the capacity.

        :param id: The ID of the nodegroup.
        :param ami_type: (experimental) The AMI type for your node group. Default: - auto-determined from the instanceType property.
        :param desired_size: (experimental) The current number of worker nodes that the managed node group should maintain. If not specified, the nodewgroup will initially create ``minSize`` instances. Default: 2
        :param disk_size: (experimental) The root device disk size (in GiB) for your node group instances. Default: 20
        :param force_update: (experimental) Force the update if the existing node group's pods are unable to be drained due to a pod disruption budget issue. If an update fails because pods could not be drained, you can force the update after it fails to terminate the old node whether or not any pods are running on the node. Default: true
        :param instance_type: (experimental) The instance type to use for your node group. Currently, you can specify a single instance type for a node group. The default value for this parameter is ``t3.medium``. If you choose a GPU instance type, be sure to specify the ``AL2_x86_64_GPU`` with the amiType parameter. Default: t3.medium
        :param labels: (experimental) The Kubernetes labels to be applied to the nodes in the node group when they are created. Default: - None
        :param launch_template_spec: (experimental) Launch template specification used for the nodegroup. Default: - no launch template
        :param max_size: (experimental) The maximum number of worker nodes that the managed node group can scale out to. Managed node groups can support up to 100 nodes by default. Default: - desiredSize
        :param min_size: (experimental) The minimum number of worker nodes that the managed node group can scale in to. This number must be greater than zero. Default: 1
        :param nodegroup_name: (experimental) Name of the Nodegroup. Default: - resource ID
        :param node_role: (experimental) The IAM role to associate with your node group. The Amazon EKS worker node kubelet daemon makes calls to AWS APIs on your behalf. Worker nodes receive permissions for these API calls through an IAM instance profile and associated policies. Before you can launch worker nodes and register them into a cluster, you must create an IAM role for those worker nodes to use when they are launched. Default: - None. Auto-generated if not specified.
        :param release_version: (experimental) The AMI version of the Amazon EKS-optimized AMI to use with your node group (for example, ``1.14.7-YYYYMMDD``). Default: - The latest available AMI version for the node group's current Kubernetes version is used.
        :param remote_access: (experimental) The remote access (SSH) configuration to use with your node group. Disabled by default, however, if you specify an Amazon EC2 SSH key but do not specify a source security group when you create a managed node group, then port 22 on the worker nodes is opened to the internet (0.0.0.0/0) Default: - disabled
        :param subnets: (experimental) The subnets to use for the Auto Scaling group that is created for your node group. By specifying the SubnetSelection, the selected subnets will automatically apply required tags i.e. ``kubernetes.io/cluster/CLUSTER_NAME`` with a value of ``shared``, where ``CLUSTER_NAME`` is replaced with the name of your cluster. Default: - private subnets
        :param tags: (experimental) The metadata to apply to the node group to assist with categorization and organization. Each tag consists of a key and an optional value, both of which you define. Node group tags do not propagate to any other resources associated with the node group, such as the Amazon EC2 instances or subnets. Default: - None

        :see: https://docs.aws.amazon.com/eks/latest/userguide/managed-node-groups.html
        :stability: experimental
        """
        options = NodegroupOptions(
            ami_type=ami_type,
            desired_size=desired_size,
            disk_size=disk_size,
            force_update=force_update,
            instance_type=instance_type,
            labels=labels,
            launch_template_spec=launch_template_spec,
            max_size=max_size,
            min_size=min_size,
            nodegroup_name=nodegroup_name,
            node_role=node_role,
            release_version=release_version,
            remote_access=remote_access,
            subnets=subnets,
            tags=tags,
        )

        return jsii.invoke(self, "addNodegroupCapacity", [id, options])

    @jsii.member(jsii_name="addServiceAccount")
    def add_service_account(
        self,
        id: builtins.str,
        *,
        name: typing.Optional[builtins.str] = None,
        namespace: typing.Optional[builtins.str] = None,
    ) -> ServiceAccount:
        """(experimental) Creates a new service account with corresponding IAM Role (IRSA).

        :param id: -
        :param name: (experimental) The name of the service account. Default: - If no name is given, it will use the id of the resource.
        :param namespace: (experimental) The namespace of the service account. Default: "default"

        :stability: experimental
        """
        options = ServiceAccountOptions(name=name, namespace=namespace)

        return jsii.invoke(self, "addServiceAccount", [id, options])

    @jsii.member(jsii_name="connectAutoScalingGroupCapacity")
    def connect_auto_scaling_group_capacity(
        self,
        auto_scaling_group: aws_cdk.aws_autoscaling.AutoScalingGroup,
        *,
        bootstrap_enabled: typing.Optional[builtins.bool] = None,
        bootstrap_options: typing.Optional[BootstrapOptions] = None,
        machine_image_type: typing.Optional[MachineImageType] = None,
        map_role: typing.Optional[builtins.bool] = None,
    ) -> None:
        """(experimental) Connect capacity in the form of an existing AutoScalingGroup to the EKS cluster.

        The AutoScalingGroup must be running an EKS-optimized AMI containing the
        /etc/eks/bootstrap.sh script. This method will configure Security Groups,
        add the right policies to the instance role, apply the right tags, and add
        the required user data to the instance's launch configuration.

        Spot instances will be labeled ``lifecycle=Ec2Spot`` and tainted with ``PreferNoSchedule``.
        If kubectl is enabled, the
        `spot interrupt handler <https://github.com/awslabs/ec2-spot-labs/tree/master/ec2-spot-eks-solution/spot-termination-handler>`_
        daemon will be installed on all spot instances to handle
        `EC2 Spot Instance Termination Notices <https://aws.amazon.com/blogs/aws/new-ec2-spot-instance-termination-notices/>`_.

        Prefer to use ``addAutoScalingGroupCapacity`` if possible.

        :param auto_scaling_group: [disable-awslint:ref-via-interface].
        :param bootstrap_enabled: (experimental) Configures the EC2 user-data script for instances in this autoscaling group to bootstrap the node (invoke ``/etc/eks/bootstrap.sh``) and associate it with the EKS cluster. If you wish to provide a custom user data script, set this to ``false`` and manually invoke ``autoscalingGroup.addUserData()``. Default: true
        :param bootstrap_options: (experimental) Allows options for node bootstrapping through EC2 user data. Default: - default options
        :param machine_image_type: (experimental) Allow options to specify different machine image type. Default: MachineImageType.AMAZON_LINUX_2
        :param map_role: (experimental) Will automatically update the aws-auth ConfigMap to map the IAM instance role to RBAC. This cannot be explicitly set to ``true`` if the cluster has kubectl disabled. Default: - true if the cluster has kubectl enabled (which is the default).

        :see: https://docs.aws.amazon.com/eks/latest/userguide/launch-workers.html
        :stability: experimental
        """
        options = AutoScalingGroupOptions(
            bootstrap_enabled=bootstrap_enabled,
            bootstrap_options=bootstrap_options,
            machine_image_type=machine_image_type,
            map_role=map_role,
        )

        return jsii.invoke(self, "connectAutoScalingGroupCapacity", [auto_scaling_group, options])

    @jsii.member(jsii_name="getServiceLoadBalancerAddress")
    def get_service_load_balancer_address(
        self,
        service_name: builtins.str,
        *,
        namespace: typing.Optional[builtins.str] = None,
        timeout: typing.Optional[aws_cdk.core.Duration] = None,
    ) -> builtins.str:
        """(experimental) Fetch the load balancer address of a service of type 'LoadBalancer'.

        :param service_name: The name of the service.
        :param namespace: (experimental) The namespace the service belongs to. Default: 'default'
        :param timeout: (experimental) Timeout for waiting on the load balancer address. Default: Duration.minutes(5)

        :stability: experimental
        """
        options = ServiceLoadBalancerAddressOptions(
            namespace=namespace, timeout=timeout
        )

        return jsii.invoke(self, "getServiceLoadBalancerAddress", [service_name, options])

    @builtins.property # type: ignore
    @jsii.member(jsii_name="adminRole")
    def admin_role(self) -> aws_cdk.aws_iam.Role:
        """(experimental) An IAM role with administrative permissions to create or update the cluster.

        This role also has ``systems:master`` permissions.

        :stability: experimental
        """
        return jsii.get(self, "adminRole")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="awsAuth")
    def aws_auth(self) -> AwsAuth:
        """(experimental) Lazily creates the AwsAuth resource, which manages AWS authentication mapping.

        :stability: experimental
        """
        return jsii.get(self, "awsAuth")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterArn")
    def cluster_arn(self) -> builtins.str:
        """(experimental) The AWS generated ARN for the Cluster resource.

        :stability: experimental

        Example::

            # Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
            arn:aws:eks:us-west-2666666666666cluster / prod
        """
        return jsii.get(self, "clusterArn")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterCertificateAuthorityData")
    def cluster_certificate_authority_data(self) -> builtins.str:
        """(experimental) The certificate-authority-data for your cluster.

        :stability: experimental
        """
        return jsii.get(self, "clusterCertificateAuthorityData")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterEncryptionConfigKeyArn")
    def cluster_encryption_config_key_arn(self) -> builtins.str:
        """(experimental) Amazon Resource Name (ARN) or alias of the customer master key (CMK).

        :stability: experimental
        """
        return jsii.get(self, "clusterEncryptionConfigKeyArn")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterEndpoint")
    def cluster_endpoint(self) -> builtins.str:
        """(experimental) The endpoint URL for the Cluster.

        This is the URL inside the kubeconfig file to use with kubectl

        :stability: experimental

        Example::

            # Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
            https:
        """
        return jsii.get(self, "clusterEndpoint")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterName")
    def cluster_name(self) -> builtins.str:
        """(experimental) The Name of the created EKS Cluster.

        :stability: experimental
        """
        return jsii.get(self, "clusterName")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterOpenIdConnectIssuer")
    def cluster_open_id_connect_issuer(self) -> builtins.str:
        """(experimental) If this cluster is kubectl-enabled, returns the OpenID Connect issuer.

        This is because the values is only be retrieved by the API and not exposed
        by CloudFormation. If this cluster is not kubectl-enabled (i.e. uses the
        stock ``CfnCluster``), this is ``undefined``.

        :stability: experimental
        :attribute: true
        """
        return jsii.get(self, "clusterOpenIdConnectIssuer")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterOpenIdConnectIssuerUrl")
    def cluster_open_id_connect_issuer_url(self) -> builtins.str:
        """(experimental) If this cluster is kubectl-enabled, returns the OpenID Connect issuer url.

        This is because the values is only be retrieved by the API and not exposed
        by CloudFormation. If this cluster is not kubectl-enabled (i.e. uses the
        stock ``CfnCluster``), this is ``undefined``.

        :stability: experimental
        :attribute: true
        """
        return jsii.get(self, "clusterOpenIdConnectIssuerUrl")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterSecurityGroup")
    def cluster_security_group(self) -> aws_cdk.aws_ec2.ISecurityGroup:
        """(experimental) The cluster security group that was created by Amazon EKS for the cluster.

        :stability: experimental
        """
        return jsii.get(self, "clusterSecurityGroup")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="clusterSecurityGroupId")
    def cluster_security_group_id(self) -> builtins.str:
        """(experimental) The id of the cluster security group that was created by Amazon EKS for the cluster.

        :stability: experimental
        """
        return jsii.get(self, "clusterSecurityGroupId")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="connections")
    def connections(self) -> aws_cdk.aws_ec2.Connections:
        """(experimental) Manages connection rules (Security Group Rules) for the cluster.

        :stability: experimental
        :memberof: Cluster
        :type: {ec2.Connections}
        """
        return jsii.get(self, "connections")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="openIdConnectProvider")
    def open_id_connect_provider(self) -> aws_cdk.aws_iam.IOpenIdConnectProvider:
        """(experimental) An ``OpenIdConnectProvider`` resource associated with this cluster, and which can be used to link this cluster to AWS IAM.

        A provider will only be defined if this property is accessed (lazy initialization).

        :stability: experimental
        """
        return jsii.get(self, "openIdConnectProvider")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="prune")
    def prune(self) -> builtins.bool:
        """(experimental) Determines if Kubernetes resources can be pruned automatically.

        :stability: experimental
        """
        return jsii.get(self, "prune")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="role")
    def role(self) -> aws_cdk.aws_iam.IRole:
        """(experimental) IAM role assumed by the EKS Control Plane.

        :stability: experimental
        """
        return jsii.get(self, "role")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="vpc")
    def vpc(self) -> aws_cdk.aws_ec2.IVpc:
        """(experimental) The VPC in which this Cluster was created.

        :stability: experimental
        """
        return jsii.get(self, "vpc")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="defaultCapacity")
    def default_capacity(
        self,
    ) -> typing.Optional[aws_cdk.aws_autoscaling.AutoScalingGroup]:
        """(experimental) The auto scaling group that hosts the default capacity for this cluster.

        This will be ``undefined`` if the ``defaultCapacityType`` is not ``EC2`` or
        ``defaultCapacityType`` is ``EC2`` but default capacity is set to 0.

        :stability: experimental
        """
        return jsii.get(self, "defaultCapacity")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="defaultNodegroup")
    def default_nodegroup(self) -> typing.Optional[Nodegroup]:
        """(experimental) The node group that hosts the default capacity for this cluster.

        This will be ``undefined`` if the ``defaultCapacityType`` is ``EC2`` or
        ``defaultCapacityType`` is ``NODEGROUP`` but default capacity is set to 0.

        :stability: experimental
        """
        return jsii.get(self, "defaultNodegroup")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="kubectlEnvironment")
    def kubectl_environment(
        self,
    ) -> typing.Optional[typing.Mapping[builtins.str, builtins.str]]:
        """(experimental) Custom environment variables when running ``kubectl`` against this cluster.

        :stability: experimental
        """
        return jsii.get(self, "kubectlEnvironment")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="kubectlLayer")
    def kubectl_layer(self) -> typing.Optional[aws_cdk.aws_lambda.ILayerVersion]:
        """(experimental) The AWS Lambda layer that contains ``kubectl``, ``helm`` and the AWS CLI.

        If
        undefined, a SAR app that contains this layer will be used.

        :stability: experimental
        """
        return jsii.get(self, "kubectlLayer")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="kubectlMemory")
    def kubectl_memory(self) -> typing.Optional[aws_cdk.core.Size]:
        """(experimental) The amount of memory allocated to the kubectl provider's lambda function.

        :stability: experimental
        """
        return jsii.get(self, "kubectlMemory")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="kubectlPrivateSubnets")
    def kubectl_private_subnets(
        self,
    ) -> typing.Optional[typing.List[aws_cdk.aws_ec2.ISubnet]]:
        """(experimental) Subnets to host the ``kubectl`` compute resources.

        :default:

        - If not specified, the k8s endpoint is expected to be accessible
        publicly.

        :stability: experimental
        """
        return jsii.get(self, "kubectlPrivateSubnets")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="kubectlRole")
    def kubectl_role(self) -> typing.Optional[aws_cdk.aws_iam.IRole]:
        """(experimental) An IAM role that can perform kubectl operations against this cluster.

        The role should be mapped to the ``system:masters`` Kubernetes RBAC role.

        :stability: experimental
        """
        return jsii.get(self, "kubectlRole")

    @builtins.property # type: ignore
    @jsii.member(jsii_name="kubectlSecurityGroup")
    def kubectl_security_group(self) -> typing.Optional[aws_cdk.aws_ec2.ISecurityGroup]:
        """(experimental) A security group to use for ``kubectl`` execution.

        :default:

        - If not specified, the k8s endpoint is expected to be accessible
        publicly.

        :stability: experimental
        """
        return jsii.get(self, "kubectlSecurityGroup")


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.ClusterOptions",
    jsii_struct_bases=[CommonClusterOptions],
    name_mapping={
        "version": "version",
        "cluster_name": "clusterName",
        "output_cluster_name": "outputClusterName",
        "output_config_command": "outputConfigCommand",
        "role": "role",
        "security_group": "securityGroup",
        "vpc": "vpc",
        "vpc_subnets": "vpcSubnets",
        "cluster_handler_environment": "clusterHandlerEnvironment",
        "core_dns_compute_type": "coreDnsComputeType",
        "endpoint_access": "endpointAccess",
        "kubectl_environment": "kubectlEnvironment",
        "kubectl_layer": "kubectlLayer",
        "kubectl_memory": "kubectlMemory",
        "masters_role": "mastersRole",
        "output_masters_role_arn": "outputMastersRoleArn",
        "place_cluster_handler_in_vpc": "placeClusterHandlerInVpc",
        "prune": "prune",
    },
)
class ClusterOptions(CommonClusterOptions):
    def __init__(
        self,
        *,
        version: KubernetesVersion,
        cluster_name: typing.Optional[builtins.str] = None,
        output_cluster_name: typing.Optional[builtins.bool] = None,
        output_config_command: typing.Optional[builtins.bool] = None,
        role: typing.Optional[aws_cdk.aws_iam.IRole] = None,
        security_group: typing.Optional[aws_cdk.aws_ec2.ISecurityGroup] = None,
        vpc: typing.Optional[aws_cdk.aws_ec2.IVpc] = None,
        vpc_subnets: typing.Optional[typing.List[aws_cdk.aws_ec2.SubnetSelection]] = None,
        cluster_handler_environment: typing.Optional[typing.Mapping[builtins.str, builtins.str]] = None,
        core_dns_compute_type: typing.Optional[CoreDnsComputeType] = None,
        endpoint_access: typing.Optional[EndpointAccess] = None,
        kubectl_environment: typing.Optional[typing.Mapping[builtins.str, builtins.str]] = None,
        kubectl_layer: typing.Optional[aws_cdk.aws_lambda.ILayerVersion] = None,
        kubectl_memory: typing.Optional[aws_cdk.core.Size] = None,
        masters_role: typing.Optional[aws_cdk.aws_iam.IRole] = None,
        output_masters_role_arn: typing.Optional[builtins.bool] = None,
        place_cluster_handler_in_vpc: typing.Optional[builtins.bool] = None,
        prune: typing.Optional[builtins.bool] = None,
    ) -> None:
        """(experimental) Options for EKS clusters.

        :param version: (experimental) The Kubernetes version to run in the cluster.
        :param cluster_name: (experimental) Name for the cluster. Default: - Automatically generated name
        :param output_cluster_name: (experimental) Determines whether a CloudFormation output with the name of the cluster will be synthesized. Default: false
        :param output_config_command: (experimental) Determines whether a CloudFormation output with the ``aws eks update-kubeconfig`` command will be synthesized. This command will include the cluster name and, if applicable, the ARN of the masters IAM role. Default: true
        :param role: (experimental) Role that provides permissions for the Kubernetes control plane to make calls to AWS API operations on your behalf. Default: - A role is automatically created for you
        :param security_group: (experimental) Security Group to use for Control Plane ENIs. Default: - A security group is automatically created
        :param vpc: (experimental) The VPC in which to create the Cluster. Default: - a VPC with default configuration will be created and can be accessed through ``cluster.vpc``.
        :param vpc_subnets: (experimental) Where to place EKS Control Plane ENIs. If you want to create public load balancers, this must include public subnets. For example, to only select private subnets, supply the following:: vpcSubnets: [ { subnetType: ec2.SubnetType.Private } ] Default: - All public and private subnets
        :param cluster_handler_environment: (experimental) Custom environment variables when interacting with the EKS endpoint to manage the cluster lifecycle. Default: - No environment variables.
        :param core_dns_compute_type: (experimental) Controls the "eks.amazonaws.com/compute-type" annotation in the CoreDNS configuration on your cluster to determine which compute type to use for CoreDNS. Default: CoreDnsComputeType.EC2 (for ``FargateCluster`` the default is FARGATE)
        :param endpoint_access: (experimental) Configure access to the Kubernetes API server endpoint.. Default: EndpointAccess.PUBLIC_AND_PRIVATE
        :param kubectl_environment: (experimental) Environment variables for the kubectl execution. Only relevant for kubectl enabled clusters. Default: - No environment variables.
        :param kubectl_layer: (experimental) An AWS Lambda Layer which includes ``kubectl``, Helm and the AWS CLI. By default, the provider will use the layer included in the "aws-lambda-layer-kubectl" SAR application which is available in all commercial regions. To deploy the layer locally, visit https://github.com/aws-samples/aws-lambda-layer-kubectl/blob/master/cdk/README.md for instructions on how to prepare the .zip file and then define it in your app as follows:: const layer = new lambda.LayerVersion(this, 'kubectl-layer', { code: lambda.Code.fromAsset(`${__dirname}/layer.zip`)), compatibleRuntimes: [lambda.Runtime.PROVIDED] }) Default: - the layer provided by the ``aws-lambda-layer-kubectl`` SAR app.
        :param kubectl_memory: (experimental) Amount of memory to allocate to the provider's lambda function. Default: Size.gibibytes(1)
        :param masters_role: (experimental) An IAM role that will be added to the ``system:masters`` Kubernetes RBAC group. Default: - a role that assumable by anyone with permissions in the same account will automatically be defined
        :param output_masters_role_arn: (experimental) Determines whether a CloudFormation output with the ARN of the "masters" IAM role will be synthesized (if ``mastersRole`` is specified). Default: false
        :param place_cluster_handler_in_vpc: (experimental) If set to true, the cluster handler functions will be placed in the private subnets of the cluster vpc, subject to the ``vpcSubnets`` selection strategy. Default: false
        :param prune: (experimental) Indicates whether Kubernetes resources added through ``addManifest()`` can be automatically pruned. When this is enabled (default), prune labels will be allocated and injected to each resource. These labels will then be used when issuing the ``kubectl apply`` operation with the ``--prune`` switch. Default: true

        :stability: experimental
        """
        self._values: typing.Dict[str, typing.Any] = {
            "version": version,
        }
        if cluster_name is not None:
            self._values["cluster_name"] = cluster_name
        if output_cluster_name is not None:
            self._values["output_cluster_name"] = output_cluster_name
        if output_config_command is not None:
            self._values["output_config_command"] = output_config_command
        if role is not None:
            self._values["role"] = role
        if security_group is not None:
            self._values["security_group"] = security_group
        if vpc is not None:
            self._values["vpc"] = vpc
        if vpc_subnets is not None:
            self._values["vpc_subnets"] = vpc_subnets
        if cluster_handler_environment is not None:
            self._values["cluster_handler_environment"] = cluster_handler_environment
        if core_dns_compute_type is not None:
            self._values["core_dns_compute_type"] = core_dns_compute_type
        if endpoint_access is not None:
            self._values["endpoint_access"] = endpoint_access
        if kubectl_environment is not None:
            self._values["kubectl_environment"] = kubectl_environment
        if kubectl_layer is not None:
            self._values["kubectl_layer"] = kubectl_layer
        if kubectl_memory is not None:
            self._values["kubectl_memory"] = kubectl_memory
        if masters_role is not None:
            self._values["masters_role"] = masters_role
        if output_masters_role_arn is not None:
            self._values["output_masters_role_arn"] = output_masters_role_arn
        if place_cluster_handler_in_vpc is not None:
            self._values["place_cluster_handler_in_vpc"] = place_cluster_handler_in_vpc
        if prune is not None:
            self._values["prune"] = prune

    @builtins.property
    def version(self) -> KubernetesVersion:
        """(experimental) The Kubernetes version to run in the cluster.

        :stability: experimental
        """
        result = self._values.get("version")
        assert result is not None, "Required property 'version' is missing"
        return result

    @builtins.property
    def cluster_name(self) -> typing.Optional[builtins.str]:
        """(experimental) Name for the cluster.

        :default: - Automatically generated name

        :stability: experimental
        """
        result = self._values.get("cluster_name")
        return result

    @builtins.property
    def output_cluster_name(self) -> typing.Optional[builtins.bool]:
        """(experimental) Determines whether a CloudFormation output with the name of the cluster will be synthesized.

        :default: false

        :stability: experimental
        """
        result = self._values.get("output_cluster_name")
        return result

    @builtins.property
    def output_config_command(self) -> typing.Optional[builtins.bool]:
        """(experimental) Determines whether a CloudFormation output with the ``aws eks update-kubeconfig`` command will be synthesized.

        This command will include
        the cluster name and, if applicable, the ARN of the masters IAM role.

        :default: true

        :stability: experimental
        """
        result = self._values.get("output_config_command")
        return result

    @builtins.property
    def role(self) -> typing.Optional[aws_cdk.aws_iam.IRole]:
        """(experimental) Role that provides permissions for the Kubernetes control plane to make calls to AWS API operations on your behalf.

        :default: - A role is automatically created for you

        :stability: experimental
        """
        result = self._values.get("role")
        return result

    @builtins.property
    def security_group(self) -> typing.Optional[aws_cdk.aws_ec2.ISecurityGroup]:
        """(experimental) Security Group to use for Control Plane ENIs.

        :default: - A security group is automatically created

        :stability: experimental
        """
        result = self._values.get("security_group")
        return result

    @builtins.property
    def vpc(self) -> typing.Optional[aws_cdk.aws_ec2.IVpc]:
        """(experimental) The VPC in which to create the Cluster.

        :default: - a VPC with default configuration will be created and can be accessed through ``cluster.vpc``.

        :stability: experimental
        """
        result = self._values.get("vpc")
        return result

    @builtins.property
    def vpc_subnets(
        self,
    ) -> typing.Optional[typing.List[aws_cdk.aws_ec2.SubnetSelection]]:
        """(experimental) Where to place EKS Control Plane ENIs.

        If you want to create public load balancers, this must include public subnets.

        For example, to only select private subnets, supply the following::

           # Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
           vpcSubnets: [
              { subnetType: ec2.SubnetType.Private }
           ]

        :default: - All public and private subnets

        :stability: experimental
        """
        result = self._values.get("vpc_subnets")
        return result

    @builtins.property
    def cluster_handler_environment(
        self,
    ) -> typing.Optional[typing.Mapping[builtins.str, builtins.str]]:
        """(experimental) Custom environment variables when interacting with the EKS endpoint to manage the cluster lifecycle.

        :default: - No environment variables.

        :stability: experimental
        """
        result = self._values.get("cluster_handler_environment")
        return result

    @builtins.property
    def core_dns_compute_type(self) -> typing.Optional[CoreDnsComputeType]:
        """(experimental) Controls the "eks.amazonaws.com/compute-type" annotation in the CoreDNS configuration on your cluster to determine which compute type to use for CoreDNS.

        :default: CoreDnsComputeType.EC2 (for ``FargateCluster`` the default is FARGATE)

        :stability: experimental
        """
        result = self._values.get("core_dns_compute_type")
        return result

    @builtins.property
    def endpoint_access(self) -> typing.Optional[EndpointAccess]:
        """(experimental) Configure access to the Kubernetes API server endpoint..

        :default: EndpointAccess.PUBLIC_AND_PRIVATE

        :see: https://docs.aws.amazon.com/eks/latest/userguide/cluster-endpoint.html
        :stability: experimental
        """
        result = self._values.get("endpoint_access")
        return result

    @builtins.property
    def kubectl_environment(
        self,
    ) -> typing.Optional[typing.Mapping[builtins.str, builtins.str]]:
        """(experimental) Environment variables for the kubectl execution.

        Only relevant for kubectl enabled clusters.

        :default: - No environment variables.

        :stability: experimental
        """
        result = self._values.get("kubectl_environment")
        return result

    @builtins.property
    def kubectl_layer(self) -> typing.Optional[aws_cdk.aws_lambda.ILayerVersion]:
        """(experimental) An AWS Lambda Layer which includes ``kubectl``, Helm and the AWS CLI.

        By default, the provider will use the layer included in the
        "aws-lambda-layer-kubectl" SAR application which is available in all
        commercial regions.

        To deploy the layer locally, visit
        https://github.com/aws-samples/aws-lambda-layer-kubectl/blob/master/cdk/README.md
        for instructions on how to prepare the .zip file and then define it in your
        app as follows::

           # Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
           layer = lambda_.LayerVersion(self, "kubectl-layer",
               code=lambda_.Code.from_asset(f"{__dirname}/layer.zip")
           )
           compatible_runtimes =

        :default: - the layer provided by the ``aws-lambda-layer-kubectl`` SAR app.

        :see: https://github.com/aws-samples/aws-lambda-layer-kubectl
        :stability: experimental
        """
        result = self._values.get("kubectl_layer")
        return result

    @builtins.property
    def kubectl_memory(self) -> typing.Optional[aws_cdk.core.Size]:
        """(experimental) Amount of memory to allocate to the provider's lambda function.

        :default: Size.gibibytes(1)

        :stability: experimental
        """
        result = self._values.get("kubectl_memory")
        return result

    @builtins.property
    def masters_role(self) -> typing.Optional[aws_cdk.aws_iam.IRole]:
        """(experimental) An IAM role that will be added to the ``system:masters`` Kubernetes RBAC group.

        :default:

        - a role that assumable by anyone with permissions in the same
        account will automatically be defined

        :see: https://kubernetes.io/docs/reference/access-authn-authz/rbac/#default-roles-and-role-bindings
        :stability: experimental
        """
        result = self._values.get("masters_role")
        return result

    @builtins.property
    def output_masters_role_arn(self) -> typing.Optional[builtins.bool]:
        """(experimental) Determines whether a CloudFormation output with the ARN of the "masters" IAM role will be synthesized (if ``mastersRole`` is specified).

        :default: false

        :stability: experimental
        """
        result = self._values.get("output_masters_role_arn")
        return result

    @builtins.property
    def place_cluster_handler_in_vpc(self) -> typing.Optional[builtins.bool]:
        """(experimental) If set to true, the cluster handler functions will be placed in the private subnets of the cluster vpc, subject to the ``vpcSubnets`` selection strategy.

        :default: false

        :stability: experimental
        """
        result = self._values.get("place_cluster_handler_in_vpc")
        return result

    @builtins.property
    def prune(self) -> typing.Optional[builtins.bool]:
        """(experimental) Indicates whether Kubernetes resources added through ``addManifest()`` can be automatically pruned.

        When this is enabled (default), prune labels will be
        allocated and injected to each resource. These labels will then be used
        when issuing the ``kubectl apply`` operation with the ``--prune`` switch.

        :default: true

        :stability: experimental
        """
        result = self._values.get("prune")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "ClusterOptions(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.ClusterProps",
    jsii_struct_bases=[ClusterOptions],
    name_mapping={
        "version": "version",
        "cluster_name": "clusterName",
        "output_cluster_name": "outputClusterName",
        "output_config_command": "outputConfigCommand",
        "role": "role",
        "security_group": "securityGroup",
        "vpc": "vpc",
        "vpc_subnets": "vpcSubnets",
        "cluster_handler_environment": "clusterHandlerEnvironment",
        "core_dns_compute_type": "coreDnsComputeType",
        "endpoint_access": "endpointAccess",
        "kubectl_environment": "kubectlEnvironment",
        "kubectl_layer": "kubectlLayer",
        "kubectl_memory": "kubectlMemory",
        "masters_role": "mastersRole",
        "output_masters_role_arn": "outputMastersRoleArn",
        "place_cluster_handler_in_vpc": "placeClusterHandlerInVpc",
        "prune": "prune",
        "default_capacity": "defaultCapacity",
        "default_capacity_instance": "defaultCapacityInstance",
        "default_capacity_type": "defaultCapacityType",
        "secrets_encryption_key": "secretsEncryptionKey",
    },
)
class ClusterProps(ClusterOptions):
    def __init__(
        self,
        *,
        version: KubernetesVersion,
        cluster_name: typing.Optional[builtins.str] = None,
        output_cluster_name: typing.Optional[builtins.bool] = None,
        output_config_command: typing.Optional[builtins.bool] = None,
        role: typing.Optional[aws_cdk.aws_iam.IRole] = None,
        security_group: typing.Optional[aws_cdk.aws_ec2.ISecurityGroup] = None,
        vpc: typing.Optional[aws_cdk.aws_ec2.IVpc] = None,
        vpc_subnets: typing.Optional[typing.List[aws_cdk.aws_ec2.SubnetSelection]] = None,
        cluster_handler_environment: typing.Optional[typing.Mapping[builtins.str, builtins.str]] = None,
        core_dns_compute_type: typing.Optional[CoreDnsComputeType] = None,
        endpoint_access: typing.Optional[EndpointAccess] = None,
        kubectl_environment: typing.Optional[typing.Mapping[builtins.str, builtins.str]] = None,
        kubectl_layer: typing.Optional[aws_cdk.aws_lambda.ILayerVersion] = None,
        kubectl_memory: typing.Optional[aws_cdk.core.Size] = None,
        masters_role: typing.Optional[aws_cdk.aws_iam.IRole] = None,
        output_masters_role_arn: typing.Optional[builtins.bool] = None,
        place_cluster_handler_in_vpc: typing.Optional[builtins.bool] = None,
        prune: typing.Optional[builtins.bool] = None,
        default_capacity: typing.Optional[jsii.Number] = None,
        default_capacity_instance: typing.Optional[aws_cdk.aws_ec2.InstanceType] = None,
        default_capacity_type: typing.Optional[DefaultCapacityType] = None,
        secrets_encryption_key: typing.Optional[aws_cdk.aws_kms.IKey] = None,
    ) -> None:
        """(experimental) Common configuration props for EKS clusters.

        :param version: (experimental) The Kubernetes version to run in the cluster.
        :param cluster_name: (experimental) Name for the cluster. Default: - Automatically generated name
        :param output_cluster_name: (experimental) Determines whether a CloudFormation output with the name of the cluster will be synthesized. Default: false
        :param output_config_command: (experimental) Determines whether a CloudFormation output with the ``aws eks update-kubeconfig`` command will be synthesized. This command will include the cluster name and, if applicable, the ARN of the masters IAM role. Default: true
        :param role: (experimental) Role that provides permissions for the Kubernetes control plane to make calls to AWS API operations on your behalf. Default: - A role is automatically created for you
        :param security_group: (experimental) Security Group to use for Control Plane ENIs. Default: - A security group is automatically created
        :param vpc: (experimental) The VPC in which to create the Cluster. Default: - a VPC with default configuration will be created and can be accessed through ``cluster.vpc``.
        :param vpc_subnets: (experimental) Where to place EKS Control Plane ENIs. If you want to create public load balancers, this must include public subnets. For example, to only select private subnets, supply the following:: vpcSubnets: [ { subnetType: ec2.SubnetType.Private } ] Default: - All public and private subnets
        :param cluster_handler_environment: (experimental) Custom environment variables when interacting with the EKS endpoint to manage the cluster lifecycle. Default: - No environment variables.
        :param core_dns_compute_type: (experimental) Controls the "eks.amazonaws.com/compute-type" annotation in the CoreDNS configuration on your cluster to determine which compute type to use for CoreDNS. Default: CoreDnsComputeType.EC2 (for ``FargateCluster`` the default is FARGATE)
        :param endpoint_access: (experimental) Configure access to the Kubernetes API server endpoint.. Default: EndpointAccess.PUBLIC_AND_PRIVATE
        :param kubectl_environment: (experimental) Environment variables for the kubectl execution. Only relevant for kubectl enabled clusters. Default: - No environment variables.
        :param kubectl_layer: (experimental) An AWS Lambda Layer which includes ``kubectl``, Helm and the AWS CLI. By default, the provider will use the layer included in the "aws-lambda-layer-kubectl" SAR application which is available in all commercial regions. To deploy the layer locally, visit https://github.com/aws-samples/aws-lambda-layer-kubectl/blob/master/cdk/README.md for instructions on how to prepare the .zip file and then define it in your app as follows:: const layer = new lambda.LayerVersion(this, 'kubectl-layer', { code: lambda.Code.fromAsset(`${__dirname}/layer.zip`)), compatibleRuntimes: [lambda.Runtime.PROVIDED] }) Default: - the layer provided by the ``aws-lambda-layer-kubectl`` SAR app.
        :param kubectl_memory: (experimental) Amount of memory to allocate to the provider's lambda function. Default: Size.gibibytes(1)
        :param masters_role: (experimental) An IAM role that will be added to the ``system:masters`` Kubernetes RBAC group. Default: - a role that assumable by anyone with permissions in the same account will automatically be defined
        :param output_masters_role_arn: (experimental) Determines whether a CloudFormation output with the ARN of the "masters" IAM role will be synthesized (if ``mastersRole`` is specified). Default: false
        :param place_cluster_handler_in_vpc: (experimental) If set to true, the cluster handler functions will be placed in the private subnets of the cluster vpc, subject to the ``vpcSubnets`` selection strategy. Default: false
        :param prune: (experimental) Indicates whether Kubernetes resources added through ``addManifest()`` can be automatically pruned. When this is enabled (default), prune labels will be allocated and injected to each resource. These labels will then be used when issuing the ``kubectl apply`` operation with the ``--prune`` switch. Default: true
        :param default_capacity: (experimental) Number of instances to allocate as an initial capacity for this cluster. Instance type can be configured through ``defaultCapacityInstanceType``, which defaults to ``m5.large``. Use ``cluster.addAutoScalingGroupCapacity`` to add additional customized capacity. Set this to ``0`` is you wish to avoid the initial capacity allocation. Default: 2
        :param default_capacity_instance: (experimental) The instance type to use for the default capacity. This will only be taken into account if ``defaultCapacity`` is > 0. Default: m5.large
        :param default_capacity_type: (experimental) The default capacity type for the cluster. Default: NODEGROUP
        :param secrets_encryption_key: (experimental) KMS secret for envelope encryption for Kubernetes secrets. Default: - By default, Kubernetes stores all secret object data within etcd and all etcd volumes used by Amazon EKS are encrypted at the disk-level using AWS-Managed encryption keys.

        :stability: experimental
        """
        self._values: typing.Dict[str, typing.Any] = {
            "version": version,
        }
        if cluster_name is not None:
            self._values["cluster_name"] = cluster_name
        if output_cluster_name is not None:
            self._values["output_cluster_name"] = output_cluster_name
        if output_config_command is not None:
            self._values["output_config_command"] = output_config_command
        if role is not None:
            self._values["role"] = role
        if security_group is not None:
            self._values["security_group"] = security_group
        if vpc is not None:
            self._values["vpc"] = vpc
        if vpc_subnets is not None:
            self._values["vpc_subnets"] = vpc_subnets
        if cluster_handler_environment is not None:
            self._values["cluster_handler_environment"] = cluster_handler_environment
        if core_dns_compute_type is not None:
            self._values["core_dns_compute_type"] = core_dns_compute_type
        if endpoint_access is not None:
            self._values["endpoint_access"] = endpoint_access
        if kubectl_environment is not None:
            self._values["kubectl_environment"] = kubectl_environment
        if kubectl_layer is not None:
            self._values["kubectl_layer"] = kubectl_layer
        if kubectl_memory is not None:
            self._values["kubectl_memory"] = kubectl_memory
        if masters_role is not None:
            self._values["masters_role"] = masters_role
        if output_masters_role_arn is not None:
            self._values["output_masters_role_arn"] = output_masters_role_arn
        if place_cluster_handler_in_vpc is not None:
            self._values["place_cluster_handler_in_vpc"] = place_cluster_handler_in_vpc
        if prune is not None:
            self._values["prune"] = prune
        if default_capacity is not None:
            self._values["default_capacity"] = default_capacity
        if default_capacity_instance is not None:
            self._values["default_capacity_instance"] = default_capacity_instance
        if default_capacity_type is not None:
            self._values["default_capacity_type"] = default_capacity_type
        if secrets_encryption_key is not None:
            self._values["secrets_encryption_key"] = secrets_encryption_key

    @builtins.property
    def version(self) -> KubernetesVersion:
        """(experimental) The Kubernetes version to run in the cluster.

        :stability: experimental
        """
        result = self._values.get("version")
        assert result is not None, "Required property 'version' is missing"
        return result

    @builtins.property
    def cluster_name(self) -> typing.Optional[builtins.str]:
        """(experimental) Name for the cluster.

        :default: - Automatically generated name

        :stability: experimental
        """
        result = self._values.get("cluster_name")
        return result

    @builtins.property
    def output_cluster_name(self) -> typing.Optional[builtins.bool]:
        """(experimental) Determines whether a CloudFormation output with the name of the cluster will be synthesized.

        :default: false

        :stability: experimental
        """
        result = self._values.get("output_cluster_name")
        return result

    @builtins.property
    def output_config_command(self) -> typing.Optional[builtins.bool]:
        """(experimental) Determines whether a CloudFormation output with the ``aws eks update-kubeconfig`` command will be synthesized.

        This command will include
        the cluster name and, if applicable, the ARN of the masters IAM role.

        :default: true

        :stability: experimental
        """
        result = self._values.get("output_config_command")
        return result

    @builtins.property
    def role(self) -> typing.Optional[aws_cdk.aws_iam.IRole]:
        """(experimental) Role that provides permissions for the Kubernetes control plane to make calls to AWS API operations on your behalf.

        :default: - A role is automatically created for you

        :stability: experimental
        """
        result = self._values.get("role")
        return result

    @builtins.property
    def security_group(self) -> typing.Optional[aws_cdk.aws_ec2.ISecurityGroup]:
        """(experimental) Security Group to use for Control Plane ENIs.

        :default: - A security group is automatically created

        :stability: experimental
        """
        result = self._values.get("security_group")
        return result

    @builtins.property
    def vpc(self) -> typing.Optional[aws_cdk.aws_ec2.IVpc]:
        """(experimental) The VPC in which to create the Cluster.

        :default: - a VPC with default configuration will be created and can be accessed through ``cluster.vpc``.

        :stability: experimental
        """
        result = self._values.get("vpc")
        return result

    @builtins.property
    def vpc_subnets(
        self,
    ) -> typing.Optional[typing.List[aws_cdk.aws_ec2.SubnetSelection]]:
        """(experimental) Where to place EKS Control Plane ENIs.

        If you want to create public load balancers, this must include public subnets.

        For example, to only select private subnets, supply the following::

           # Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
           vpcSubnets: [
              { subnetType: ec2.SubnetType.Private }
           ]

        :default: - All public and private subnets

        :stability: experimental
        """
        result = self._values.get("vpc_subnets")
        return result

    @builtins.property
    def cluster_handler_environment(
        self,
    ) -> typing.Optional[typing.Mapping[builtins.str, builtins.str]]:
        """(experimental) Custom environment variables when interacting with the EKS endpoint to manage the cluster lifecycle.

        :default: - No environment variables.

        :stability: experimental
        """
        result = self._values.get("cluster_handler_environment")
        return result

    @builtins.property
    def core_dns_compute_type(self) -> typing.Optional[CoreDnsComputeType]:
        """(experimental) Controls the "eks.amazonaws.com/compute-type" annotation in the CoreDNS configuration on your cluster to determine which compute type to use for CoreDNS.

        :default: CoreDnsComputeType.EC2 (for ``FargateCluster`` the default is FARGATE)

        :stability: experimental
        """
        result = self._values.get("core_dns_compute_type")
        return result

    @builtins.property
    def endpoint_access(self) -> typing.Optional[EndpointAccess]:
        """(experimental) Configure access to the Kubernetes API server endpoint..

        :default: EndpointAccess.PUBLIC_AND_PRIVATE

        :see: https://docs.aws.amazon.com/eks/latest/userguide/cluster-endpoint.html
        :stability: experimental
        """
        result = self._values.get("endpoint_access")
        return result

    @builtins.property
    def kubectl_environment(
        self,
    ) -> typing.Optional[typing.Mapping[builtins.str, builtins.str]]:
        """(experimental) Environment variables for the kubectl execution.

        Only relevant for kubectl enabled clusters.

        :default: - No environment variables.

        :stability: experimental
        """
        result = self._values.get("kubectl_environment")
        return result

    @builtins.property
    def kubectl_layer(self) -> typing.Optional[aws_cdk.aws_lambda.ILayerVersion]:
        """(experimental) An AWS Lambda Layer which includes ``kubectl``, Helm and the AWS CLI.

        By default, the provider will use the layer included in the
        "aws-lambda-layer-kubectl" SAR application which is available in all
        commercial regions.

        To deploy the layer locally, visit
        https://github.com/aws-samples/aws-lambda-layer-kubectl/blob/master/cdk/README.md
        for instructions on how to prepare the .zip file and then define it in your
        app as follows::

           # Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
           layer = lambda_.LayerVersion(self, "kubectl-layer",
               code=lambda_.Code.from_asset(f"{__dirname}/layer.zip")
           )
           compatible_runtimes =

        :default: - the layer provided by the ``aws-lambda-layer-kubectl`` SAR app.

        :see: https://github.com/aws-samples/aws-lambda-layer-kubectl
        :stability: experimental
        """
        result = self._values.get("kubectl_layer")
        return result

    @builtins.property
    def kubectl_memory(self) -> typing.Optional[aws_cdk.core.Size]:
        """(experimental) Amount of memory to allocate to the provider's lambda function.

        :default: Size.gibibytes(1)

        :stability: experimental
        """
        result = self._values.get("kubectl_memory")
        return result

    @builtins.property
    def masters_role(self) -> typing.Optional[aws_cdk.aws_iam.IRole]:
        """(experimental) An IAM role that will be added to the ``system:masters`` Kubernetes RBAC group.

        :default:

        - a role that assumable by anyone with permissions in the same
        account will automatically be defined

        :see: https://kubernetes.io/docs/reference/access-authn-authz/rbac/#default-roles-and-role-bindings
        :stability: experimental
        """
        result = self._values.get("masters_role")
        return result

    @builtins.property
    def output_masters_role_arn(self) -> typing.Optional[builtins.bool]:
        """(experimental) Determines whether a CloudFormation output with the ARN of the "masters" IAM role will be synthesized (if ``mastersRole`` is specified).

        :default: false

        :stability: experimental
        """
        result = self._values.get("output_masters_role_arn")
        return result

    @builtins.property
    def place_cluster_handler_in_vpc(self) -> typing.Optional[builtins.bool]:
        """(experimental) If set to true, the cluster handler functions will be placed in the private subnets of the cluster vpc, subject to the ``vpcSubnets`` selection strategy.

        :default: false

        :stability: experimental
        """
        result = self._values.get("place_cluster_handler_in_vpc")
        return result

    @builtins.property
    def prune(self) -> typing.Optional[builtins.bool]:
        """(experimental) Indicates whether Kubernetes resources added through ``addManifest()`` can be automatically pruned.

        When this is enabled (default), prune labels will be
        allocated and injected to each resource. These labels will then be used
        when issuing the ``kubectl apply`` operation with the ``--prune`` switch.

        :default: true

        :stability: experimental
        """
        result = self._values.get("prune")
        return result

    @builtins.property
    def default_capacity(self) -> typing.Optional[jsii.Number]:
        """(experimental) Number of instances to allocate as an initial capacity for this cluster.

        Instance type can be configured through ``defaultCapacityInstanceType``,
        which defaults to ``m5.large``.

        Use ``cluster.addAutoScalingGroupCapacity`` to add additional customized capacity. Set this
        to ``0`` is you wish to avoid the initial capacity allocation.

        :default: 2

        :stability: experimental
        """
        result = self._values.get("default_capacity")
        return result

    @builtins.property
    def default_capacity_instance(
        self,
    ) -> typing.Optional[aws_cdk.aws_ec2.InstanceType]:
        """(experimental) The instance type to use for the default capacity.

        This will only be taken
        into account if ``defaultCapacity`` is > 0.

        :default: m5.large

        :stability: experimental
        """
        result = self._values.get("default_capacity_instance")
        return result

    @builtins.property
    def default_capacity_type(self) -> typing.Optional[DefaultCapacityType]:
        """(experimental) The default capacity type for the cluster.

        :default: NODEGROUP

        :stability: experimental
        """
        result = self._values.get("default_capacity_type")
        return result

    @builtins.property
    def secrets_encryption_key(self) -> typing.Optional[aws_cdk.aws_kms.IKey]:
        """(experimental) KMS secret for envelope encryption for Kubernetes secrets.

        :default:

        - By default, Kubernetes stores all secret object data within etcd and
        all etcd volumes used by Amazon EKS are encrypted at the disk-level
        using AWS-Managed encryption keys.

        :stability: experimental
        """
        result = self._values.get("secrets_encryption_key")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "ClusterProps(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


class FargateCluster(
    Cluster,
    metaclass=jsii.JSIIMeta,
    jsii_type="@aws-cdk/aws-eks.FargateCluster",
):
    """(experimental) Defines an EKS cluster that runs entirely on AWS Fargate.

    The cluster is created with a default Fargate Profile that matches the
    "default" and "kube-system" namespaces. You can add additional profiles using
    ``addFargateProfile``.

    :stability: experimental
    """

    def __init__(
        self,
        scope: constructs.Construct,
        id: builtins.str,
        *,
        default_profile: typing.Optional[FargateProfileOptions] = None,
        cluster_handler_environment: typing.Optional[typing.Mapping[builtins.str, builtins.str]] = None,
        core_dns_compute_type: typing.Optional[CoreDnsComputeType] = None,
        endpoint_access: typing.Optional[EndpointAccess] = None,
        kubectl_environment: typing.Optional[typing.Mapping[builtins.str, builtins.str]] = None,
        kubectl_layer: typing.Optional[aws_cdk.aws_lambda.ILayerVersion] = None,
        kubectl_memory: typing.Optional[aws_cdk.core.Size] = None,
        masters_role: typing.Optional[aws_cdk.aws_iam.IRole] = None,
        output_masters_role_arn: typing.Optional[builtins.bool] = None,
        place_cluster_handler_in_vpc: typing.Optional[builtins.bool] = None,
        prune: typing.Optional[builtins.bool] = None,
        version: KubernetesVersion,
        cluster_name: typing.Optional[builtins.str] = None,
        output_cluster_name: typing.Optional[builtins.bool] = None,
        output_config_command: typing.Optional[builtins.bool] = None,
        role: typing.Optional[aws_cdk.aws_iam.IRole] = None,
        security_group: typing.Optional[aws_cdk.aws_ec2.ISecurityGroup] = None,
        vpc: typing.Optional[aws_cdk.aws_ec2.IVpc] = None,
        vpc_subnets: typing.Optional[typing.List[aws_cdk.aws_ec2.SubnetSelection]] = None,
    ) -> None:
        """
        :param scope: -
        :param id: -
        :param default_profile: (experimental) Fargate Profile to create along with the cluster. Default: - A profile called "default" with 'default' and 'kube-system' selectors will be created if this is left undefined.
        :param cluster_handler_environment: (experimental) Custom environment variables when interacting with the EKS endpoint to manage the cluster lifecycle. Default: - No environment variables.
        :param core_dns_compute_type: (experimental) Controls the "eks.amazonaws.com/compute-type" annotation in the CoreDNS configuration on your cluster to determine which compute type to use for CoreDNS. Default: CoreDnsComputeType.EC2 (for ``FargateCluster`` the default is FARGATE)
        :param endpoint_access: (experimental) Configure access to the Kubernetes API server endpoint.. Default: EndpointAccess.PUBLIC_AND_PRIVATE
        :param kubectl_environment: (experimental) Environment variables for the kubectl execution. Only relevant for kubectl enabled clusters. Default: - No environment variables.
        :param kubectl_layer: (experimental) An AWS Lambda Layer which includes ``kubectl``, Helm and the AWS CLI. By default, the provider will use the layer included in the "aws-lambda-layer-kubectl" SAR application which is available in all commercial regions. To deploy the layer locally, visit https://github.com/aws-samples/aws-lambda-layer-kubectl/blob/master/cdk/README.md for instructions on how to prepare the .zip file and then define it in your app as follows:: const layer = new lambda.LayerVersion(this, 'kubectl-layer', { code: lambda.Code.fromAsset(`${__dirname}/layer.zip`)), compatibleRuntimes: [lambda.Runtime.PROVIDED] }) Default: - the layer provided by the ``aws-lambda-layer-kubectl`` SAR app.
        :param kubectl_memory: (experimental) Amount of memory to allocate to the provider's lambda function. Default: Size.gibibytes(1)
        :param masters_role: (experimental) An IAM role that will be added to the ``system:masters`` Kubernetes RBAC group. Default: - a role that assumable by anyone with permissions in the same account will automatically be defined
        :param output_masters_role_arn: (experimental) Determines whether a CloudFormation output with the ARN of the "masters" IAM role will be synthesized (if ``mastersRole`` is specified). Default: false
        :param place_cluster_handler_in_vpc: (experimental) If set to true, the cluster handler functions will be placed in the private subnets of the cluster vpc, subject to the ``vpcSubnets`` selection strategy. Default: false
        :param prune: (experimental) Indicates whether Kubernetes resources added through ``addManifest()`` can be automatically pruned. When this is enabled (default), prune labels will be allocated and injected to each resource. These labels will then be used when issuing the ``kubectl apply`` operation with the ``--prune`` switch. Default: true
        :param version: (experimental) The Kubernetes version to run in the cluster.
        :param cluster_name: (experimental) Name for the cluster. Default: - Automatically generated name
        :param output_cluster_name: (experimental) Determines whether a CloudFormation output with the name of the cluster will be synthesized. Default: false
        :param output_config_command: (experimental) Determines whether a CloudFormation output with the ``aws eks update-kubeconfig`` command will be synthesized. This command will include the cluster name and, if applicable, the ARN of the masters IAM role. Default: true
        :param role: (experimental) Role that provides permissions for the Kubernetes control plane to make calls to AWS API operations on your behalf. Default: - A role is automatically created for you
        :param security_group: (experimental) Security Group to use for Control Plane ENIs. Default: - A security group is automatically created
        :param vpc: (experimental) The VPC in which to create the Cluster. Default: - a VPC with default configuration will be created and can be accessed through ``cluster.vpc``.
        :param vpc_subnets: (experimental) Where to place EKS Control Plane ENIs. If you want to create public load balancers, this must include public subnets. For example, to only select private subnets, supply the following:: vpcSubnets: [ { subnetType: ec2.SubnetType.Private } ] Default: - All public and private subnets

        :stability: experimental
        """
        props = FargateClusterProps(
            default_profile=default_profile,
            cluster_handler_environment=cluster_handler_environment,
            core_dns_compute_type=core_dns_compute_type,
            endpoint_access=endpoint_access,
            kubectl_environment=kubectl_environment,
            kubectl_layer=kubectl_layer,
            kubectl_memory=kubectl_memory,
            masters_role=masters_role,
            output_masters_role_arn=output_masters_role_arn,
            place_cluster_handler_in_vpc=place_cluster_handler_in_vpc,
            prune=prune,
            version=version,
            cluster_name=cluster_name,
            output_cluster_name=output_cluster_name,
            output_config_command=output_config_command,
            role=role,
            security_group=security_group,
            vpc=vpc,
            vpc_subnets=vpc_subnets,
        )

        jsii.create(FargateCluster, self, [scope, id, props])


@jsii.data_type(
    jsii_type="@aws-cdk/aws-eks.FargateClusterProps",
    jsii_struct_bases=[ClusterOptions],
    name_mapping={
        "version": "version",
        "cluster_name": "clusterName",
        "output_cluster_name": "outputClusterName",
        "output_config_command": "outputConfigCommand",
        "role": "role",
        "security_group": "securityGroup",
        "vpc": "vpc",
        "vpc_subnets": "vpcSubnets",
        "cluster_handler_environment": "clusterHandlerEnvironment",
        "core_dns_compute_type": "coreDnsComputeType",
        "endpoint_access": "endpointAccess",
        "kubectl_environment": "kubectlEnvironment",
        "kubectl_layer": "kubectlLayer",
        "kubectl_memory": "kubectlMemory",
        "masters_role": "mastersRole",
        "output_masters_role_arn": "outputMastersRoleArn",
        "place_cluster_handler_in_vpc": "placeClusterHandlerInVpc",
        "prune": "prune",
        "default_profile": "defaultProfile",
    },
)
class FargateClusterProps(ClusterOptions):
    def __init__(
        self,
        *,
        version: KubernetesVersion,
        cluster_name: typing.Optional[builtins.str] = None,
        output_cluster_name: typing.Optional[builtins.bool] = None,
        output_config_command: typing.Optional[builtins.bool] = None,
        role: typing.Optional[aws_cdk.aws_iam.IRole] = None,
        security_group: typing.Optional[aws_cdk.aws_ec2.ISecurityGroup] = None,
        vpc: typing.Optional[aws_cdk.aws_ec2.IVpc] = None,
        vpc_subnets: typing.Optional[typing.List[aws_cdk.aws_ec2.SubnetSelection]] = None,
        cluster_handler_environment: typing.Optional[typing.Mapping[builtins.str, builtins.str]] = None,
        core_dns_compute_type: typing.Optional[CoreDnsComputeType] = None,
        endpoint_access: typing.Optional[EndpointAccess] = None,
        kubectl_environment: typing.Optional[typing.Mapping[builtins.str, builtins.str]] = None,
        kubectl_layer: typing.Optional[aws_cdk.aws_lambda.ILayerVersion] = None,
        kubectl_memory: typing.Optional[aws_cdk.core.Size] = None,
        masters_role: typing.Optional[aws_cdk.aws_iam.IRole] = None,
        output_masters_role_arn: typing.Optional[builtins.bool] = None,
        place_cluster_handler_in_vpc: typing.Optional[builtins.bool] = None,
        prune: typing.Optional[builtins.bool] = None,
        default_profile: typing.Optional[FargateProfileOptions] = None,
    ) -> None:
        """(experimental) Configuration props for EKS Fargate.

        :param version: (experimental) The Kubernetes version to run in the cluster.
        :param cluster_name: (experimental) Name for the cluster. Default: - Automatically generated name
        :param output_cluster_name: (experimental) Determines whether a CloudFormation output with the name of the cluster will be synthesized. Default: false
        :param output_config_command: (experimental) Determines whether a CloudFormation output with the ``aws eks update-kubeconfig`` command will be synthesized. This command will include the cluster name and, if applicable, the ARN of the masters IAM role. Default: true
        :param role: (experimental) Role that provides permissions for the Kubernetes control plane to make calls to AWS API operations on your behalf. Default: - A role is automatically created for you
        :param security_group: (experimental) Security Group to use for Control Plane ENIs. Default: - A security group is automatically created
        :param vpc: (experimental) The VPC in which to create the Cluster. Default: - a VPC with default configuration will be created and can be accessed through ``cluster.vpc``.
        :param vpc_subnets: (experimental) Where to place EKS Control Plane ENIs. If you want to create public load balancers, this must include public subnets. For example, to only select private subnets, supply the following:: vpcSubnets: [ { subnetType: ec2.SubnetType.Private } ] Default: - All public and private subnets
        :param cluster_handler_environment: (experimental) Custom environment variables when interacting with the EKS endpoint to manage the cluster lifecycle. Default: - No environment variables.
        :param core_dns_compute_type: (experimental) Controls the "eks.amazonaws.com/compute-type" annotation in the CoreDNS configuration on your cluster to determine which compute type to use for CoreDNS. Default: CoreDnsComputeType.EC2 (for ``FargateCluster`` the default is FARGATE)
        :param endpoint_access: (experimental) Configure access to the Kubernetes API server endpoint.. Default: EndpointAccess.PUBLIC_AND_PRIVATE
        :param kubectl_environment: (experimental) Environment variables for the kubectl execution. Only relevant for kubectl enabled clusters. Default: - No environment variables.
        :param kubectl_layer: (experimental) An AWS Lambda Layer which includes ``kubectl``, Helm and the AWS CLI. By default, the provider will use the layer included in the "aws-lambda-layer-kubectl" SAR application which is available in all commercial regions. To deploy the layer locally, visit https://github.com/aws-samples/aws-lambda-layer-kubectl/blob/master/cdk/README.md for instructions on how to prepare the .zip file and then define it in your app as follows:: const layer = new lambda.LayerVersion(this, 'kubectl-layer', { code: lambda.Code.fromAsset(`${__dirname}/layer.zip`)), compatibleRuntimes: [lambda.Runtime.PROVIDED] }) Default: - the layer provided by the ``aws-lambda-layer-kubectl`` SAR app.
        :param kubectl_memory: (experimental) Amount of memory to allocate to the provider's lambda function. Default: Size.gibibytes(1)
        :param masters_role: (experimental) An IAM role that will be added to the ``system:masters`` Kubernetes RBAC group. Default: - a role that assumable by anyone with permissions in the same account will automatically be defined
        :param output_masters_role_arn: (experimental) Determines whether a CloudFormation output with the ARN of the "masters" IAM role will be synthesized (if ``mastersRole`` is specified). Default: false
        :param place_cluster_handler_in_vpc: (experimental) If set to true, the cluster handler functions will be placed in the private subnets of the cluster vpc, subject to the ``vpcSubnets`` selection strategy. Default: false
        :param prune: (experimental) Indicates whether Kubernetes resources added through ``addManifest()`` can be automatically pruned. When this is enabled (default), prune labels will be allocated and injected to each resource. These labels will then be used when issuing the ``kubectl apply`` operation with the ``--prune`` switch. Default: true
        :param default_profile: (experimental) Fargate Profile to create along with the cluster. Default: - A profile called "default" with 'default' and 'kube-system' selectors will be created if this is left undefined.

        :stability: experimental
        """
        if isinstance(default_profile, dict):
            default_profile = FargateProfileOptions(**default_profile)
        self._values: typing.Dict[str, typing.Any] = {
            "version": version,
        }
        if cluster_name is not None:
            self._values["cluster_name"] = cluster_name
        if output_cluster_name is not None:
            self._values["output_cluster_name"] = output_cluster_name
        if output_config_command is not None:
            self._values["output_config_command"] = output_config_command
        if role is not None:
            self._values["role"] = role
        if security_group is not None:
            self._values["security_group"] = security_group
        if vpc is not None:
            self._values["vpc"] = vpc
        if vpc_subnets is not None:
            self._values["vpc_subnets"] = vpc_subnets
        if cluster_handler_environment is not None:
            self._values["cluster_handler_environment"] = cluster_handler_environment
        if core_dns_compute_type is not None:
            self._values["core_dns_compute_type"] = core_dns_compute_type
        if endpoint_access is not None:
            self._values["endpoint_access"] = endpoint_access
        if kubectl_environment is not None:
            self._values["kubectl_environment"] = kubectl_environment
        if kubectl_layer is not None:
            self._values["kubectl_layer"] = kubectl_layer
        if kubectl_memory is not None:
            self._values["kubectl_memory"] = kubectl_memory
        if masters_role is not None:
            self._values["masters_role"] = masters_role
        if output_masters_role_arn is not None:
            self._values["output_masters_role_arn"] = output_masters_role_arn
        if place_cluster_handler_in_vpc is not None:
            self._values["place_cluster_handler_in_vpc"] = place_cluster_handler_in_vpc
        if prune is not None:
            self._values["prune"] = prune
        if default_profile is not None:
            self._values["default_profile"] = default_profile

    @builtins.property
    def version(self) -> KubernetesVersion:
        """(experimental) The Kubernetes version to run in the cluster.

        :stability: experimental
        """
        result = self._values.get("version")
        assert result is not None, "Required property 'version' is missing"
        return result

    @builtins.property
    def cluster_name(self) -> typing.Optional[builtins.str]:
        """(experimental) Name for the cluster.

        :default: - Automatically generated name

        :stability: experimental
        """
        result = self._values.get("cluster_name")
        return result

    @builtins.property
    def output_cluster_name(self) -> typing.Optional[builtins.bool]:
        """(experimental) Determines whether a CloudFormation output with the name of the cluster will be synthesized.

        :default: false

        :stability: experimental
        """
        result = self._values.get("output_cluster_name")
        return result

    @builtins.property
    def output_config_command(self) -> typing.Optional[builtins.bool]:
        """(experimental) Determines whether a CloudFormation output with the ``aws eks update-kubeconfig`` command will be synthesized.

        This command will include
        the cluster name and, if applicable, the ARN of the masters IAM role.

        :default: true

        :stability: experimental
        """
        result = self._values.get("output_config_command")
        return result

    @builtins.property
    def role(self) -> typing.Optional[aws_cdk.aws_iam.IRole]:
        """(experimental) Role that provides permissions for the Kubernetes control plane to make calls to AWS API operations on your behalf.

        :default: - A role is automatically created for you

        :stability: experimental
        """
        result = self._values.get("role")
        return result

    @builtins.property
    def security_group(self) -> typing.Optional[aws_cdk.aws_ec2.ISecurityGroup]:
        """(experimental) Security Group to use for Control Plane ENIs.

        :default: - A security group is automatically created

        :stability: experimental
        """
        result = self._values.get("security_group")
        return result

    @builtins.property
    def vpc(self) -> typing.Optional[aws_cdk.aws_ec2.IVpc]:
        """(experimental) The VPC in which to create the Cluster.

        :default: - a VPC with default configuration will be created and can be accessed through ``cluster.vpc``.

        :stability: experimental
        """
        result = self._values.get("vpc")
        return result

    @builtins.property
    def vpc_subnets(
        self,
    ) -> typing.Optional[typing.List[aws_cdk.aws_ec2.SubnetSelection]]:
        """(experimental) Where to place EKS Control Plane ENIs.

        If you want to create public load balancers, this must include public subnets.

        For example, to only select private subnets, supply the following::

           # Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
           vpcSubnets: [
              { subnetType: ec2.SubnetType.Private }
           ]

        :default: - All public and private subnets

        :stability: experimental
        """
        result = self._values.get("vpc_subnets")
        return result

    @builtins.property
    def cluster_handler_environment(
        self,
    ) -> typing.Optional[typing.Mapping[builtins.str, builtins.str]]:
        """(experimental) Custom environment variables when interacting with the EKS endpoint to manage the cluster lifecycle.

        :default: - No environment variables.

        :stability: experimental
        """
        result = self._values.get("cluster_handler_environment")
        return result

    @builtins.property
    def core_dns_compute_type(self) -> typing.Optional[CoreDnsComputeType]:
        """(experimental) Controls the "eks.amazonaws.com/compute-type" annotation in the CoreDNS configuration on your cluster to determine which compute type to use for CoreDNS.

        :default: CoreDnsComputeType.EC2 (for ``FargateCluster`` the default is FARGATE)

        :stability: experimental
        """
        result = self._values.get("core_dns_compute_type")
        return result

    @builtins.property
    def endpoint_access(self) -> typing.Optional[EndpointAccess]:
        """(experimental) Configure access to the Kubernetes API server endpoint..

        :default: EndpointAccess.PUBLIC_AND_PRIVATE

        :see: https://docs.aws.amazon.com/eks/latest/userguide/cluster-endpoint.html
        :stability: experimental
        """
        result = self._values.get("endpoint_access")
        return result

    @builtins.property
    def kubectl_environment(
        self,
    ) -> typing.Optional[typing.Mapping[builtins.str, builtins.str]]:
        """(experimental) Environment variables for the kubectl execution.

        Only relevant for kubectl enabled clusters.

        :default: - No environment variables.

        :stability: experimental
        """
        result = self._values.get("kubectl_environment")
        return result

    @builtins.property
    def kubectl_layer(self) -> typing.Optional[aws_cdk.aws_lambda.ILayerVersion]:
        """(experimental) An AWS Lambda Layer which includes ``kubectl``, Helm and the AWS CLI.

        By default, the provider will use the layer included in the
        "aws-lambda-layer-kubectl" SAR application which is available in all
        commercial regions.

        To deploy the layer locally, visit
        https://github.com/aws-samples/aws-lambda-layer-kubectl/blob/master/cdk/README.md
        for instructions on how to prepare the .zip file and then define it in your
        app as follows::

           # Example automatically generated without compilation. See https://github.com/aws/jsii/issues/826
           layer = lambda_.LayerVersion(self, "kubectl-layer",
               code=lambda_.Code.from_asset(f"{__dirname}/layer.zip")
           )
           compatible_runtimes =

        :default: - the layer provided by the ``aws-lambda-layer-kubectl`` SAR app.

        :see: https://github.com/aws-samples/aws-lambda-layer-kubectl
        :stability: experimental
        """
        result = self._values.get("kubectl_layer")
        return result

    @builtins.property
    def kubectl_memory(self) -> typing.Optional[aws_cdk.core.Size]:
        """(experimental) Amount of memory to allocate to the provider's lambda function.

        :default: Size.gibibytes(1)

        :stability: experimental
        """
        result = self._values.get("kubectl_memory")
        return result

    @builtins.property
    def masters_role(self) -> typing.Optional[aws_cdk.aws_iam.IRole]:
        """(experimental) An IAM role that will be added to the ``system:masters`` Kubernetes RBAC group.

        :default:

        - a role that assumable by anyone with permissions in the same
        account will automatically be defined

        :see: https://kubernetes.io/docs/reference/access-authn-authz/rbac/#default-roles-and-role-bindings
        :stability: experimental
        """
        result = self._values.get("masters_role")
        return result

    @builtins.property
    def output_masters_role_arn(self) -> typing.Optional[builtins.bool]:
        """(experimental) Determines whether a CloudFormation output with the ARN of the "masters" IAM role will be synthesized (if ``mastersRole`` is specified).

        :default: false

        :stability: experimental
        """
        result = self._values.get("output_masters_role_arn")
        return result

    @builtins.property
    def place_cluster_handler_in_vpc(self) -> typing.Optional[builtins.bool]:
        """(experimental) If set to true, the cluster handler functions will be placed in the private subnets of the cluster vpc, subject to the ``vpcSubnets`` selection strategy.

        :default: false

        :stability: experimental
        """
        result = self._values.get("place_cluster_handler_in_vpc")
        return result

    @builtins.property
    def prune(self) -> typing.Optional[builtins.bool]:
        """(experimental) Indicates whether Kubernetes resources added through ``addManifest()`` can be automatically pruned.

        When this is enabled (default), prune labels will be
        allocated and injected to each resource. These labels will then be used
        when issuing the ``kubectl apply`` operation with the ``--prune`` switch.

        :default: true

        :stability: experimental
        """
        result = self._values.get("prune")
        return result

    @builtins.property
    def default_profile(self) -> typing.Optional[FargateProfileOptions]:
        """(experimental) Fargate Profile to create along with the cluster.

        :default:

        - A profile called "default" with 'default' and 'kube-system'
        selectors will be created if this is left undefined.

        :stability: experimental
        """
        result = self._values.get("default_profile")
        return result

    def __eq__(self, rhs: typing.Any) -> builtins.bool:
        return isinstance(rhs, self.__class__) and rhs._values == self._values

    def __ne__(self, rhs: typing.Any) -> builtins.bool:
        return not (rhs == self)

    def __repr__(self) -> str:
        return "FargateClusterProps(%s)" % ", ".join(
            k + "=" + repr(v) for k, v in self._values.items()
        )


__all__ = [
    "AutoScalingGroupCapacityOptions",
    "AutoScalingGroupOptions",
    "AwsAuth",
    "AwsAuthMapping",
    "AwsAuthProps",
    "BootstrapOptions",
    "CfnCluster",
    "CfnClusterProps",
    "CfnFargateProfile",
    "CfnFargateProfileProps",
    "CfnNodegroup",
    "CfnNodegroupProps",
    "Cluster",
    "ClusterAttributes",
    "ClusterOptions",
    "ClusterProps",
    "CommonClusterOptions",
    "CoreDnsComputeType",
    "CpuArch",
    "DefaultCapacityType",
    "EksOptimizedImage",
    "EksOptimizedImageProps",
    "EndpointAccess",
    "FargateCluster",
    "FargateClusterProps",
    "FargateProfile",
    "FargateProfileOptions",
    "FargateProfileProps",
    "HelmChart",
    "HelmChartOptions",
    "HelmChartProps",
    "ICluster",
    "INodegroup",
    "KubectlLayer",
    "KubectlLayerProps",
    "KubernetesManifest",
    "KubernetesManifestOptions",
    "KubernetesManifestProps",
    "KubernetesObjectValue",
    "KubernetesObjectValueProps",
    "KubernetesPatch",
    "KubernetesPatchProps",
    "KubernetesVersion",
    "LaunchTemplateSpec",
    "MachineImageType",
    "NodeType",
    "Nodegroup",
    "NodegroupAmiType",
    "NodegroupOptions",
    "NodegroupProps",
    "NodegroupRemoteAccess",
    "OpenIdConnectProvider",
    "OpenIdConnectProviderProps",
    "PatchType",
    "Selector",
    "ServiceAccount",
    "ServiceAccountOptions",
    "ServiceAccountProps",
    "ServiceLoadBalancerAddressOptions",
]

publication.publish()
