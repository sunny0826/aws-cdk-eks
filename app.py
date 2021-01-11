#!/usr/bin/env python3

from aws_cdk import core

from cdk_python.cdk_python_stack import CdkPythonStack

import os

app = core.App()

ACCOUNT = app.node.try_get_context('account') or os.environ.get(
    'CDK_DEFAULT_ACCOUNT', 'unknown')
REGION = app.node.try_get_context('region') or os.environ.get(
    'CDK_DEFAULT_REGION', 'unknown')

env = core.Environment(region=REGION, account=ACCOUNT)

CdkPythonStack(app, "cdk-python", env=env)

app.synth()
