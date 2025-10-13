import * as cdk from "aws-cdk-lib";
import { MiwaBackendPipelineStack } from "../lib/miwa-backend-pipeline-stack";
import { MiwaBackendStack } from "../lib/miwa-backend-stack";
import { MiwaFrontendPipelineStack } from "../lib/miwa-frontend-pipeline-stack";

const app = new cdk.App();

// Stack principal con ambos servicios
const mainStack = new MiwaBackendStack(app, "MiwaMainStack", {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION || "us-east-1",
  },
  domain: {
    hostedZoneId: process.env.HOSTED_ZONE_ID || "Z1234567890ABC",
    zoneName: process.env.DOMAIN_NAME || "example.com",
    certificateArn: process.env.CERTIFICATE_ARN,
    subdomain: process.env.SUBDOMAIN || "app",
  },
});

// Pipeline para el Backend
const backendPipeline = new MiwaBackendPipelineStack(
  app,
  "MiwaBackendPipelineStack",
  {
    env: {
      account: process.env.CDK_DEFAULT_ACCOUNT,
      region: process.env.CDK_DEFAULT_REGION || "us-east-1",
    },
    source: {
      connectionArn: process.env.GITHUB_CONNECTION_ARN!,
      repositoryOwner: process.env.BACKEND_REPO_OWNER!,
      repositoryName: process.env.BACKEND_REPO_NAME!,
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
      account: process.env.CDK_DEFAULT_ACCOUNT,
      region: process.env.CDK_DEFAULT_REGION || "us-east-1",
    },
    source: {
      connectionArn: process.env.GITHUB_CONNECTION_ARN!,
      repositoryOwner: process.env.FRONTEND_REPO_OWNER!,
      repositoryName: process.env.FRONTEND_REPO_NAME!,
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
