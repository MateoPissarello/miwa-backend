import * as cdk from "aws-cdk-lib";
import { config as loadEnv } from "dotenv";
import * as path from "path";
import { MiwaBackendPipelineStack } from "../lib/miwa-backend-pipeline-stack";
import { MiwaBackendStack } from "../lib/miwa-backend-stack";
import { MiwaFrontendPipelineStack } from "../lib/miwa-frontend-pipeline-stack";
import { MiwaGoogleTokensStack } from "../lib/miwa_google_stack";
import { MiwaLambdaS3Stack } from "../lib/miwa_lambda_stack";

loadEnv({ path: path.resolve(__dirname, "..", "..", ".env") });
const app = new cdk.App();

const requireEnv = (name: string): string => {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `Environment variable ${name} is required to synthesize the CDK app.`
    );
  }
  return value;
};

const defaultAccount = process.env.CDK_DEFAULT_ACCOUNT;
const defaultRegion = process.env.CDK_DEFAULT_REGION || "us-east-1";

const lambda_and_s3 = new MiwaLambdaS3Stack(app, "MiwaLambdaS3Stack", {
  env: {
    account: defaultAccount,
    region: defaultRegion,
  },
});
const google_stack = new MiwaGoogleTokensStack(app, "MiwaGoogleTokensStack", {
  env: {
    account: defaultAccount,
    region: defaultRegion,
  },
});

// Domain configuration (optional - for HTTPS)
const certificateArn = process.env.CERTIFICATE_ARN;
const hostedZoneId = process.env.HOSTED_ZONE_ID;
const hostedZoneName = process.env.DOMAIN_NAME;

// Stack principal con ambos servicios
const mainStack = new MiwaBackendStack(app, "MiwaBackendStack", {
  env: {
    account: defaultAccount,
    region: defaultRegion,
  },
  domain: (hostedZoneId && hostedZoneName) ? {
    hostedZoneId: hostedZoneId,
    zoneName: hostedZoneName,
    certificateArn: certificateArn,
    subdomain: process.env.SUBDOMAIN || "app",
  } : undefined,
  filesBucket: lambda_and_s3.miwaBucket,
  greeterFn: lambda_and_s3.greeterFn,
  api_endpoint: lambda_and_s3.api_endpoint,
});

mainStack.addDependency(lambda_and_s3);

const githubConnectionArn = requireEnv("GITHUB_CONNECTION_ARN");
const backendRepoOwner = requireEnv("BACKEND_REPO_OWNER");
const backendRepoName = requireEnv("BACKEND_REPO_NAME");
const frontendRepoOwner = requireEnv("FRONTEND_REPO_OWNER");
const frontendRepoName = requireEnv("FRONTEND_REPO_NAME");

// Pipeline para el Backend
const backendPipeline = new MiwaBackendPipelineStack(
  app,
  "MiwaBackendPipelineStack",
  {
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
  }
);

// Pipeline para el Frontend
const frontendPipeline = new MiwaFrontendPipelineStack(
  app,
  "MiwaFrontendPipelineStack",
  {
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
  }
);

// Dependencias
backendPipeline.addDependency(mainStack);
frontendPipeline.addDependency(mainStack);

app.synth();
