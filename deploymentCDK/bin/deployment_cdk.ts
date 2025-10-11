#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { MiwaBackendStack } from '../lib/miwa-backend-stack';

const app = new cdk.App();
new MiwaBackendStack(app, 'MiwaBackendStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION ?? 'us-east-1',
  },
});
