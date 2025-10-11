import { Duration, Stack, StackProps, CfnOutput, RemovalPolicy } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecsPatterns from 'aws-cdk-lib/aws-ecs-patterns';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as route53 from 'aws-cdk-lib/aws-route53';
import * as certificatemanager from 'aws-cdk-lib/aws-certificatemanager';
import * as ecr from 'aws-cdk-lib/aws-ecr';

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

    const vpc = new ec2.Vpc(this, 'MiwaVpc', {
      maxAzs: 2,
      natGateways: 1,
    });

    this.cluster = new ecs.Cluster(this, 'MiwaCluster', {
      vpc,
      containerInsights: true,
    });

    const logGroup = new logs.LogGroup(this, 'MiwaBackendLogs', {
      logGroupName: `/aws/ecs/miwa-backend`,
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    this.repository = new ecr.Repository(this, 'MiwaBackendRepository', {
      repositoryName: 'miwa-backend',
      imageScanOnPush: true,
      lifecycleRules: [
        {
          description: 'Retain only the 30 most recent images',
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
      domainZone = route53.HostedZone.fromHostedZoneAttributes(this, 'MiwaBackendZone', {
        hostedZoneId: props.domain.hostedZoneId,
        zoneName: props.domain.zoneName,
      });

      if (props.domain.certificateArn) {
        certificate = certificatemanager.Certificate.fromCertificateArn(
          this,
          'MiwaBackendCertificate',
          props.domain.certificateArn,
        );
      }
    }

    const imageTag = props.imageTag ?? 'latest';

    this.service = new ecsPatterns.ApplicationLoadBalancedFargateService(this, 'MiwaBackendService', {
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
        containerName: 'miwa-backend',
        containerPort: 80,
        logDriver: ecs.LogDrivers.awsLogs({
          streamPrefix: 'miwa-backend',
          logGroup,
        }),
        environment: {
          ENVIRONMENT: 'production',
        },
        image: ecs.ContainerImage.fromEcrRepository(this.repository, imageTag),
      },
    });

    this.repository.grantPull(this.service.taskDefinition.executionRole!);

    this.service.targetGroup.configureHealthCheck({
      healthyHttpCodes: '200-399',
      path: '/',
      interval: Duration.seconds(30),
      timeout: Duration.seconds(10),
      healthyThresholdCount: 2,
      unhealthyThresholdCount: 3,
    });

    const scalableTarget = this.service.service.autoScaleTaskCount({
      minCapacity: 1,
      maxCapacity: 4,
    });

    scalableTarget.scaleOnCpuUtilization('CpuScaling', {
      targetUtilizationPercent: 60,
      scaleInCooldown: Duration.seconds(60),
      scaleOutCooldown: Duration.seconds(60),
    });

    if (domainName) {
      new CfnOutput(this, 'ServiceUrl', {
        value: `https://${domainName}`,
      });
    } else {
      new CfnOutput(this, 'ServiceUrl', {
        value: `http://${this.service.loadBalancer.loadBalancerDnsName}`,
      });
    }

    new CfnOutput(this, 'EcrRepositoryUri', {
      value: this.repository.repositoryUri,
    });
  }
}
