import {
  CfnOutput,
  Duration,
  RemovalPolicy,
  Stack,
  StackProps,
} from "aws-cdk-lib";
import * as certificatemanager from "aws-cdk-lib/aws-certificatemanager";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as elasticloadbalancingv2 from "aws-cdk-lib/aws-elasticloadbalancingv2";
import * as iam from "aws-cdk-lib/aws-iam"; // Importar IAM para manejar permisos directamente
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as logs from "aws-cdk-lib/aws-logs";
import * as route53 from "aws-cdk-lib/aws-route53";
import * as route53_targets from "aws-cdk-lib/aws-route53-targets";
import * as s3 from "aws-cdk-lib/aws-s3";
import { Secret } from "aws-cdk-lib/aws-secretsmanager";
import { Construct } from "constructs";

export interface MiwaBackendStackProps extends StackProps {
  readonly cpu?: number;
  readonly memoryLimitMiB?: number;
  readonly desiredCount?: number;
  readonly domain?: MiwaBackendDomainProps;
  readonly imageTag?: string;
  readonly frontendImageTag?: string;
  readonly filesBucket?: s3.IBucket;
  readonly greeterFn?: lambda.IFunction;
  readonly api_endpoint?: string;
}

export interface MiwaBackendDomainProps {
  readonly hostedZoneId: string;
  readonly zoneName: string;
  readonly certificateArn?: string;
  readonly subdomain?: string;
}

export class MiwaBackendStack extends Stack {
  public readonly repository: ecr.Repository;
  public readonly frontendRepository: ecr.Repository;
  public readonly cluster: ecs.Cluster;
  public readonly backendService: ecs.FargateService;
  public readonly frontendService: ecs.FargateService;
  public readonly loadBalancer: elasticloadbalancingv2.ApplicationLoadBalancer;

  constructor(scope: Construct, id: string, props: MiwaBackendStackProps = {}) {
    super(scope, id, props);

    const vpc = new ec2.Vpc(this, "MiwaVpc", {
      maxAzs: 2,
      natGateways: 1,
    });

    this.cluster = new ecs.Cluster(this, "MiwaCluster", {
      vpc,
      // Se mantiene containerInsights: true aunque esté deprecated.
      containerInsights: true,
    });

    const backendLogGroup = new logs.LogGroup(this, "MiwaBackendLogs", {
      logGroupName: `/aws/ecs/miwa-backend`,
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    const frontendLogGroup = new logs.LogGroup(this, "MiwaFrontendLogs", {
      logGroupName: `/aws/ecs/miwa-frontend`,
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    // Backend Repository
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

    // Frontend Repository
    this.frontendRepository = new ecr.Repository(
      this,
      "MiwaFrontendRepository",
      {
        repositoryName: "miwa-frontend",
        imageScanOnPush: true,
        lifecycleRules: [
          {
            description: "Retain only the 30 most recent images",
            maxImageCount: 30,
          },
        ],
      }
    );

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

    const backendImageTag = props.imageTag ?? "latest";
    const frontendImageTag = props.frontendImageTag ?? "latest";

    // --- CORRECCIÓN CLAVE: Agrupar la inyección de secretos ---

    // 1. Definición de la tarea Fargate
    const backendTask = new ecs.FargateTaskDefinition(this, "backend-task", {
      memoryLimitMiB: props.memoryLimitMiB ?? 1024,
      cpu: props.cpu ?? 512,
    });

    // 2. Definición del Secreto Principal
    const mySecrets = Secret.fromSecretCompleteArn(
      this,
      `miwa-MySecret`,
      "arn:aws:secretsmanager:us-east-1:956189607462:secret:dev/miwa/app-VczjCH"
    );

    // 3. Crear una única declaración de política para leer el secreto principal
    // Esto evita que el CDK cree 15+ declaraciones que causan el error.
    backendTask.taskRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret",
        ],
        resources: [mySecrets.secretArn],
        effect: iam.Effect.ALLOW,
      })
    );

    const tokensTable = dynamodb.Table.fromTableName(
      this,
      "GoogleTokensTable",
      "miwa_google_tokens"
    );
    const transcriptionsTable = dynamodb.Table.fromTableName(
      this,
      "TranscriptionsTable",
      "transcriptions_table"
    );
    // Permisos al rol de la tarea ECS (backend)
    tokensTable.grantReadWriteData(backendTask.taskRole);
    transcriptionsTable.grantReadWriteData(backendTask.taskRole)
    const bucketFiles = props.filesBucket;
    if (bucketFiles) {
      props.filesBucket.grantReadWrite(backendTask.taskRole);
      // Si usas S3 en runtime, te puede servir pasar el nombre por env:
      // backendContainerEnv["FILES_BUCKET"] = props.filesBucket.bucketName;
    }
    const greeterFn = props.greeterFn;
    if (greeterFn) {
      backendTask.taskRole.addToPrincipalPolicy(
        new iam.PolicyStatement({
          actions: ["lambda:InvokeFunction", "lambda:InvokeAsync"],
          resources: [props.greeterFn.functionArn],
          effect: iam.Effect.ALLOW,
        })
      );
      // Si quieres, también:
      // environment: { GREETER_FN_ARN: props.greeterFn.functionArn }
    }

    // 4. Se inyectan los secretos individuales (estos son los que causan las declaraciones)
    // El CDK usará el permiso que acabamos de agregar para inyectar estos valores.
    const backendContainerSecrets: Record<string, ecs.Secret> = {};

    const secretKeys = [
      "SECRET_KEY",
      "ALGORITHM",
      "ACCESS_TOKEN_EXPIRE_MINUTES",
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
      "DYNAMO_TRANSCRIPTIONS_TABLE",
    ];

    for (const key of secretKeys) {
      // El CDK intentará agregar permisos, pero ya tiene el permiso global
      backendContainerSecrets[key] = ecs.Secret.fromSecretsManager(
        mySecrets,
        key
      );
    }

    // Load Balancer + SG
    const sg = new ec2.SecurityGroup(this, "ALB-SG", {
      vpc,
      allowAllOutbound: true,
      description: "Security group for ALB",
    });
    sg.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(80), "Allow HTTP");
    sg.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(443), "Allow HTTPS");

    this.loadBalancer = new elasticloadbalancingv2.ApplicationLoadBalancer(
      this,
      "MiwaALB",
      {
        vpc,
        internetFacing: true,
        securityGroup: sg,
      }
    );

    // Listeners (crear solo UNA instancia por puerto)
    const httpListener = this.loadBalancer.addListener("http-listener", {
      port: 80,
      protocol: elasticloadbalancingv2.ApplicationProtocol.HTTP,
    });

    let httpsListener: elasticloadbalancingv2.ApplicationListener | undefined;
    if (certificate && domainName) {
      httpsListener = this.loadBalancer.addListener("https-listener", {
        port: 443,
        protocol: elasticloadbalancingv2.ApplicationProtocol.HTTPS,
        certificates: [certificate],
      });

      // Redirección HTTP → HTTPS
      httpListener.addAction("redirect-https", {
        action: elasticloadbalancingv2.ListenerAction.redirect({
          protocol: "HTTPS",
          port: "443",
          permanent: true,
        }),
      });

      // DNS
      if (domainZone) {
        new route53.ARecord(this, "MiwaAliasRecord", {
          zone: domainZone,
          target: route53.RecordTarget.fromAlias(
            new route53_targets.LoadBalancerTarget(this.loadBalancer)
          ),
          recordName: domainName,
        });
      }
    }

    // Backend container definition
    backendTask.addContainer("miwa-backend", {
      image: ecs.ContainerImage.fromEcrRepository(
        this.repository,
        backendImageTag
      ),
      containerName: "miwa-backend",
      portMappings: [{ containerPort: 80, protocol: ecs.Protocol.TCP }],
      logging: ecs.LogDriver.awsLogs({
        streamPrefix: "miwa-backend",
        logGroup: backendLogGroup,
      }),
      environment: {
        ENVIRONMENT: "production",
        S3_BUCKET_ARN: bucketFiles?.bucketName.toString() || "",
        API_GATEWAY_URL: props.api_endpoint!,
      },
      secrets: backendContainerSecrets,
    });

    this.repository.grantPull(backendTask.executionRole!);

    // Backend Service
    this.backendService = new ecs.FargateService(this, "backend-service", {
      cluster: this.cluster,
      taskDefinition: backendTask,
      desiredCount: props.desiredCount ?? 1,
      assignPublicIp: false,
    });

    // Frontend Task Definition
    const frontendTask = new ecs.FargateTaskDefinition(this, "frontend-task", {
      memoryLimitMiB: 512,
      cpu: 256,
    });

    frontendTask.addContainer("miwa-frontend", {
      image: ecs.ContainerImage.fromEcrRepository(
        this.frontendRepository,
        frontendImageTag
      ),
      containerName: "miwa-frontend",
      portMappings: [{ containerPort: 3000, protocol: ecs.Protocol.TCP }],
      logging: ecs.LogDriver.awsLogs({
        streamPrefix: "miwa-frontend",
        logGroup: frontendLogGroup,
      }),
      environment: {
        ENVIRONMENT: "production",
        NEXT_PUBLIC_API_URL:
          certificate && domainName
            ? `https://${domainName}/api`
            : `http://${this.loadBalancer.loadBalancerDnsName}/api`,
      },
    });

    this.frontendRepository.grantPull(frontendTask.executionRole!);

    // Frontend Service
    this.frontendService = new ecs.FargateService(this, "frontend-service", {
      cluster: this.cluster,
      taskDefinition: frontendTask,
      desiredCount: 1,
      assignPublicIp: false,
    });

    // Target Groups (crear UNA vez cada uno; IDs únicos)
    const backendTargetGroup =
      new elasticloadbalancingv2.ApplicationTargetGroup(this, "backend-tg", {
        vpc,
        port: 80,
        protocol: elasticloadbalancingv2.ApplicationProtocol.HTTP,
        targetType: elasticloadbalancingv2.TargetType.IP,
        healthCheck: {
          path: "/api/health",
          interval: Duration.seconds(30),
          timeout: Duration.seconds(10),
          healthyThresholdCount: 2,
          unhealthyThresholdCount: 3,
          healthyHttpCodes: "200",
        },
      });
    backendTargetGroup.addTarget(this.backendService);

    const frontendTargetGroup =
      new elasticloadbalancingv2.ApplicationTargetGroup(this, "frontend-tg", {
        vpc,
        port: 3000,
        protocol: elasticloadbalancingv2.ApplicationProtocol.HTTP,
        targetType: elasticloadbalancingv2.TargetType.IP,
        healthCheck: {
          path: "/",
          interval: Duration.seconds(30),
          timeout: Duration.seconds(10),
          healthyThresholdCount: 2,
          unhealthyThresholdCount: 3,
          healthyHttpCodes: "200,307",
        },
      });
    frontendTargetGroup.addTarget(this.frontendService);

    // Reglas de routing (usar el listener existente; default → frontend)
    if (httpsListener) {
      // /api → backend (prioridad más alta)
      httpsListener.addTargetGroups("routes-backend", {
        conditions: [
          elasticloadbalancingv2.ListenerCondition.pathPatterns([
            "/api",
            "/api/*",
          ]),
        ],
        targetGroups: [backendTargetGroup],
        priority: 1,
      });
      
      // Default action → frontend (sin condiciones, es la acción por defecto)
      httpsListener.addAction("default-frontend", {
        action: elasticloadbalancingv2.ListenerAction.forward([frontendTargetGroup]),
      });
    } else {
      // Solo HTTP - configurar reglas con prioridades
      // /api → backend (prioridad más alta)
      httpListener.addTargetGroups("routes-backend", {
        conditions: [
          elasticloadbalancingv2.ListenerCondition.pathPatterns([
            "/api",
            "/api/*",
          ]),
        ],
        targetGroups: [backendTargetGroup],
        priority: 1,
      });
      
      // Default action → frontend (sin condiciones, es la acción por defecto)
      httpListener.addAction("default-frontend", {
        action: elasticloadbalancingv2.ListenerAction.forward([frontendTargetGroup]),
      });
    }

    // Outputs
    if (domainName) {
      new CfnOutput(this, "ServiceUrl", {
        value: `https://${domainName}`,
        description: "URL to access the application",
      });
    } else {
      new CfnOutput(this, "ServiceUrl", {
        value: `http://${this.loadBalancer.loadBalancerDnsName}`,
        description: "URL to access the application",
      });
    }

    new CfnOutput(this, "BackendRepositoryUri", {
      value: this.repository.repositoryUri,
      description: "Backend ECR repository URI",
    });

    new CfnOutput(this, "FrontendRepositoryUri", {
      value: this.frontendRepository.repositoryUri,
      description: "Frontend ECR repository URI",
    });

    new CfnOutput(this, "LoadBalancerDnsName", {
      value: this.loadBalancer.loadBalancerDnsName,
      description: "Load Balancer DNS name",
    });
  }
}
