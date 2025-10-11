#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { MiwaBackendPipelineStack } from "../lib/miwa-backend-pipeline-stack";
import { MiwaBackendStack } from "../lib/miwa-backend-stack";

const app = new cdk.App();

const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION ?? "us-east-1",
};

const backendStack = new MiwaBackendStack(app, "MiwaBackendStack", {
  env,
  domain: {
    hostedZoneId: "Z06161513HLY7BSSOJTBJ",
    zoneName: "miwa.live",
    certificateArn:
      "arn:aws:acm:us-east-1:225989373192:certificate/8b9c7396-b0b0-4a22-8b9e-9e46f5ff53f1",
    subdomain: "api",
  },
});

const pipelineContext = (app.node.tryGetContext("pipeline") as {
  readonly connectionArn?: string;
  readonly repositoryOwner?: string;
  readonly repositoryName?: string;
  readonly branch?: string;
}) ?? {
  connectionArn:
    "arn:aws:codeconnections:us-east-1:225989373192:connection/90b54923-9c02-4110-bdfa-6119ac96e412",
  branch: "main",
  repositoryName: "miwa-backend",
  repositoryOwner: "MateoPissarello",
};

const connectionArn =
  pipelineContext.connectionArn ?? process.env.GITHUB_CONNECTION_ARN;
const repositoryOwner =
  pipelineContext.repositoryOwner ?? process.env.GITHUB_REPOSITORY_OWNER;
const repositoryName =
  pipelineContext.repositoryName ?? process.env.GITHUB_REPOSITORY_NAME;
const branch =
  pipelineContext.branch ?? process.env.GITHUB_REPOSITORY_BRANCH ?? "main";

if (connectionArn && repositoryOwner && repositoryName) {
  new MiwaBackendPipelineStack(app, "MiwaBackendPipelineStack", {
    env,
    source: {
      connectionArn,
      repositoryOwner,
      repositoryName,
      branch,
    },
    repository: backendStack.repository,
    service: backendStack.service.service,
    containerName: "miwa-backend",
  });
} else {
  // eslint-disable-next-line no-console
  console.warn(
    "Skipping pipeline stack creation because GitHub connection details were not provided."
  );
}
