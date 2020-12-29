#!/usr/bin/env python3

from aws_cdk import core

from cdk_python.cdk_python_stack import CdkPythonStack


app = core.App()
CdkPythonStack(app, "cdk-python")

app.synth()
