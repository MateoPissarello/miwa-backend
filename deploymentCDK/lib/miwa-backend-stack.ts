import {
  CfnOutput,
  Duration,
  RemovalPolicy,
  Stack,
  StackProps,
} from "aws-cdk-lib";
import * as certificatemanager from "aws-cdk-lib/aws-certificatemanager";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as ecsPatterns from "aws-cdk-lib/aws-ecs-patterns";
import * as logs from "aws-cdk-lib/aws-logs";
import * as rds from "aws-cdk-lib/aws-rds";
import * as route53 from "aws-cdk-lib/aws-route53";
import { Secret } from "aws-cdk-lib/aws-secretsmanager";
import { Construct } from "constructs";

export interface MiwaBackendStackProps extends StackProps {
  readonly cpu?: number;
  readonly memoryLimitMiB?: number;
  readonly desiredCount?: number;
  readonly domain?: MiwaBackendDomainProps;
  readonly imageTag?: string;
}

export interface MiwaBackendDomainProps {
  readonly hostedZoneId: string;
  readonly zoneName: string;
  readonly certificateArn?: string;
  readonly subdomain?: string;
}

export class MiwaBackendStack extends Stack {
  public readonly repository: ecr.Repository;
  public readonly cluster: ecs.Cluster;
  public readonly service: ecsPatterns.ApplicationLoadBalancedFargateService;

  constructor(scope: Construct, id: string, props: MiwaBackendStackProps = {}) {
    super(scope, id, props);

    const vpc = new ec2.Vpc(this, "MiwaVpc", {
      maxAzs: 2,
      natGateways: 1,
    });

    this.cluster = new ecs.Cluster(this, "MiwaCluster", {
      vpc,
      containerInsights: true,
    });

    const logGroup = new logs.LogGroup(this, "MiwaBackendLogs", {
      logGroupName: `/aws/ecs/miwa-backend`,
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    const databaseName = "miwa_backend";

    const databaseSecurityGroup = new ec2.SecurityGroup(this, "MiwaDbSg", {
      vpc,
      description: "SG for MIWA Aurora Serverless v2",
      allowAllOutbound: true,
    });

    // Aurora Serverless v2 (reemplaza ServerlessCluster v1)
    const databaseCluster = new rds.DatabaseCluster(this, "MiwaDatabase", {
      engine: rds.DatabaseClusterEngine.auroraPostgres({
        // Versión soportada por Serverless v2
        version: rds.AuroraPostgresEngineVersion.VER_15_3,
      }),
      credentials: rds.Credentials.fromGeneratedSecret("postgres"),
      defaultDatabaseName: databaseName,
      writer: rds.ClusterInstance.serverlessV2("writer"),
      // readers: [rds.ClusterInstance.serverlessV2("reader")], // opcional
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      securityGroups: [databaseSecurityGroup],
      serverlessV2MinCapacity: 0.5, // ACU
      serverlessV2MaxCapacity: 8,   // ACU
      backup: { retention: Duration.days(1) },
      removalPolicy: RemovalPolicy.DESTROY,
      copyTagsToSnapshot: true,
    });

    this.repository = new ecr.Repository(this, "MiwaBackendRepository", {
      repositoryName: "miwa-backend",
      imageScanOnPush: true,
      lifecycleRules: [
        {
          description: "Retain only the 30 most recent images",
          maxImageCount: 30,
        },
      ],
    });

    let domainName: string | undefined;
    let domainZone: route53.IHostedZone | undefined;
    let certificate: certificatemanager.ICertificate | undefined;

    if (props.domain) {
      domainName = props.domain.subdomain
        ? `${props.domain.subdomain}.${props.domain.zoneName}`
        : props.domain.zoneName;
      domainZone = route53.HostedZone.fromHostedZoneAttributes(
        this,
        "MiwaBackendZone",
        {
          hostedZoneId: props.domain.hostedZoneId,
          zoneName: props.domain.zoneName,
        }
      );

      if (props.domain.certificateArn) {
        certificate = certificatemanager.Certificate.fromCertificateArn(
          this,
          "MiwaBackendCertificate",
          props.domain.certificateArn
        );
      }
    }

    const imageTag = props.imageTag ?? "latest";

    const secretKeys = [
      "SECRET_KEY",
      "ALGORITHM",
      "ACCESS_TOKEN_EXPIRE_MINUTES",
      "API_GATEWAY_URL",
      "S3_BUCKET_ARN",
      "COGNITO_USER_POOL_ID",
      "AWS_REGION",
      "COGNITO_CLIENT_ID",
      "COGNITO_SECRET",
      "GOOGLE_CLIENT_ID",
      "GOOGLE_CLIENT_SECRET",
      "GOOGLE_REDIRECT_URI",
      "GOOGLE_AFTER_CONNECT",
      "DYNAMO_GOOGLE_TOKENS_TABLE",
      "GOOGLE_STATE_SECRET",
    ];

    const mySecrets = Secret.fromSecretCompleteArn(
      this,
      `miwa-MySecret`,
      "arn:aws:secretsmanager:us-east-1:225989373192:secret:dev/miwa/app-qcbDUm"
    );

    const containerSecrets: Record<string, ecs.Secret> = {};
    for (const key of secretKeys) {
      containerSecrets[key] = ecs.Secret.fromSecretsManager(mySecrets, key);
    }

    if (databaseCluster.secret) {
      containerSecrets["DB_USER"] = ecs.Secret.fromSecretsManager(
        databaseCluster.secret,
        "username"
      );
      containerSecrets["DB_PASSWORD"] = ecs.Secret.fromSecretsManager(
        databaseCluster.secret,
        "password"
      );
      containerSecrets["DB_SECRET_ARN"] = ecs.Secret.fromSecretsManager(
        databaseCluster.secret
      );
    }

    this.service = new ecsPatterns.ApplicationLoadBalancedFargateService(
      this,
      "MiwaBackendService",
      {
        cluster: this.cluster,
        cpu: props.cpu ?? 512,
        desiredCount: props.desiredCount ?? 1,
        memoryLimitMiB: props.memoryLimitMiB ?? 1024,
        publicLoadBalancer: true,
        listenerPort: 80,
        domainName,
        domainZone,
        certificate,
        taskImageOptions: {
          containerName: "miwa-backend",
          containerPort: 80,
          logDriver: ecs.LogDrivers.awsLogs({
            streamPrefix: "miwa-backend",
            logGroup,
          }),
          environment: {
            ENVIRONMENT: "production",
            DB_HOST: databaseCluster.clusterEndpoint.hostname,
            DB_PORT: databaseCluster.clusterEndpoint.port.toString(),
            DB_NAME: databaseName,
          },
          secrets: containerSecrets,
          image: ecs.ContainerImage.fromEcrRepository(
            this.repository,
            imageTag
          ),
        },
      }
    );

    this.repository.grantPull(this.service.taskDefinition.executionRole!);

    databaseCluster.connections.allowFrom(
      this.service.service,
      ec2.Port.tcp(5432),
      "Allow ECS tasks to reach the Aurora PostgreSQL cluster"
    );

    this.service.targetGroup.configureHealthCheck({
      healthyHttpCodes: "200-399",
      path: "/",
      interval: Duration.seconds(30),
      timeout: Duration.seconds(10),
      healthyThresholdCount: 2,
      unhealthyThresholdCount: 3,
    });

    const scalableTarget = this.service.service.autoScaleTaskCount({
      minCapacity: 1,
      maxCapacity: 4,
    });

    scalableTarget.scaleOnCpuUtilization("CpuScaling", {
      targetUtilizationPercent: 60,
      scaleInCooldown: Duration.seconds(60),
      scaleOutCooldown: Duration.seconds(60),
    });

    if (domainName) {
      new CfnOutput(this, "ServiceUrl", {
        value: `https://${domainName}`,
      });
    } else {
      new CfnOutput(this, "ServiceUrl", {
        value: `http://${this.service.loadBalancer.loadBalancerDnsName}`,
      });
    }

    new CfnOutput(this, "EcrRepositoryUri", {
      value: this.repository.repositoryUri,
    });
  }
}
