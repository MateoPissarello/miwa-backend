import * as path from 'node:path';
import { Duration, Stack, StackProps, CfnOutput, RemovalPolicy } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecsPatterns from 'aws-cdk-lib/aws-ecs-patterns';
import * as logs from 'aws-cdk-lib/aws-logs';

export interface MiwaBackendStackProps extends StackProps {
  readonly cpu?: number;
  readonly memoryLimitMiB?: number;
  readonly desiredCount?: number;
}

export class MiwaBackendStack extends Stack {
  constructor(scope: Construct, id: string, props: MiwaBackendStackProps = {}) {
    super(scope, id, props);

    const vpc = new ec2.Vpc(this, 'MiwaVpc', {
      maxAzs: 2,
      natGateways: 1,
    });

    const cluster = new ecs.Cluster(this, 'MiwaCluster', {
      vpc,
      containerInsights: true,
    });

    const logGroup = new logs.LogGroup(this, 'MiwaBackendLogs', {
      logGroupName: `/aws/ecs/miwa-backend`,
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    const service = new ecsPatterns.ApplicationLoadBalancedFargateService(this, 'MiwaBackendService', {
      cluster,
      cpu: props.cpu ?? 512,
      desiredCount: props.desiredCount ?? 1,
      memoryLimitMiB: props.memoryLimitMiB ?? 1024,
      publicLoadBalancer: true,
      listenerPort: 80,
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
        image: ecs.ContainerImage.fromAsset(path.join(__dirname, '..', '..'), {
          file: 'Dockerfile',
        }),
      },
    });

    service.targetGroup.configureHealthCheck({
      healthyHttpCodes: '200-399',
      path: '/',
      interval: Duration.seconds(30),
      timeout: Duration.seconds(10),
      healthyThresholdCount: 2,
      unhealthyThresholdCount: 3,
    });

    const scalableTarget = service.service.autoScaleTaskCount({
      minCapacity: 1,
      maxCapacity: 4,
    });

    scalableTarget.scaleOnCpuUtilization('CpuScaling', {
      targetUtilizationPercent: 60,
      scaleInCooldown: Duration.seconds(60),
      scaleOutCooldown: Duration.seconds(60),
    });

    new CfnOutput(this, 'ServiceUrl', {
      value: `http://${service.loadBalancer.loadBalancerDnsName}`,
    });
  }
}
