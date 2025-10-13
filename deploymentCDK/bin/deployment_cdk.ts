import * as cdk from "aws-cdk-lib";
import { MiwaBackendPipelineStack } from "../lib/miwa-backend-pipeline-stack";
import { MiwaBackendStack } from "../lib/miwa-backend-stack";
import { MiwaFrontendPipelineStack } from "../lib/miwa-frontend-pipeline-stack";

const app = new cdk.App();

const requireEnv = (name: string): string => {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Environment variable ${name} is required to synthesize the CDK app.`);
  }
  return value;
};

const defaultAccount = process.env.CDK_DEFAULT_ACCOUNT;
const defaultRegion = process.env.CDK_DEFAULT_REGION || "us-east-1";

// Stack principal con ambos servicios
const mainStack = new MiwaBackendStack(app, "MiwaMainStack", {
  env: {
    account: defaultAccount,
    region: defaultRegion,
  },
  domain: {
    hostedZoneId: process.env.HOSTED_ZONE_ID || "Z1234567890ABC",
    zoneName: process.env.DOMAIN_NAME || "example.com",
    certificateArn: process.env.CERTIFICATE_ARN,
    subdomain: process.env.SUBDOMAIN || "app",
  },
});

const githubConnectionArn = requireEnv("GITHUB_CONNECTION_ARN");
const backendRepoOwner = requireEnv("BACKEND_REPO_OWNER");
const backendRepoName = requireEnv("BACKEND_REPO_NAME");
const frontendRepoOwner = requireEnv("FRONTEND_REPO_OWNER");
const frontendRepoName = requireEnv("FRONTEND_REPO_NAME");

// Pipeline para el Backend
const backendPipeline = new MiwaBackendPipelineStack(app, "MiwaBackendPipelineStack", {
  env: {
    account: defaultAccount,
    region: defaultRegion,
  },
  source: {
    connectionArn: githubConnectionArn,
    repositoryOwner: backendRepoOwner,
    repositoryName: backendRepoName,
    branch: process.env.BACKEND_BRANCH || "main",
  },
  repository: mainStack.repository,
  service: mainStack.backendService,
  containerName: "miwa-backend",
});

// Pipeline para el Frontend
const frontendPipeline = new MiwaFrontendPipelineStack(app, "MiwaFrontendPipelineStack", {
  env: {
    account: defaultAccount,
    region: defaultRegion,
  },
  source: {
    connectionArn: githubConnectionArn,
    repositoryOwner: frontendRepoOwner,
    repositoryName: frontendRepoName,
    branch: process.env.FRONTEND_BRANCH || "main",
  },
  repository: mainStack.frontendRepository,
  service: mainStack.frontendService,
  containerName: "miwa-frontend",
});

// Dependencias
backendPipeline.addDependency(mainStack);
frontendPipeline.addDependency(mainStack);

app.synth();
