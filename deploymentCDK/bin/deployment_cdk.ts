#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { MiwaBackendStack } from '../lib/miwa-backend-stack';
import { MiwaBackendPipelineStack } from '../lib/miwa-backend-pipeline-stack';

const app = new cdk.App();

const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION ?? 'us-east-1',
};

const backendStack = new MiwaBackendStack(app, 'MiwaBackendStack', {
  env,
});

const pipelineContext = (app.node.tryGetContext('pipeline') as {
  readonly connectionArn?: string;
  readonly repositoryOwner?: string;
  readonly repositoryName?: string;
  readonly branch?: string;
}) ?? {};

const connectionArn = pipelineContext.connectionArn ?? process.env.GITHUB_CONNECTION_ARN;
const repositoryOwner = pipelineContext.repositoryOwner ?? process.env.GITHUB_REPOSITORY_OWNER;
const repositoryName = pipelineContext.repositoryName ?? process.env.GITHUB_REPOSITORY_NAME;
const branch = pipelineContext.branch ?? process.env.GITHUB_REPOSITORY_BRANCH ?? 'main';

if (connectionArn && repositoryOwner && repositoryName) {
  new MiwaBackendPipelineStack(app, 'MiwaBackendPipelineStack', {
    env,
    source: {
      connectionArn,
      repositoryOwner,
      repositoryName,
      branch,
    },
    repository: backendStack.repository,
    service: backendStack.service.service,
    containerName: 'miwa-backend',
  });
} else {
  // eslint-disable-next-line no-console
  console.warn('Skipping pipeline stack creation because GitHub connection details were not provided.');
}
