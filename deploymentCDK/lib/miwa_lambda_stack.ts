import { PythonFunction } from "@aws-cdk/aws-lambda-python-alpha";
import * as cdk from "aws-cdk-lib";
import { Duration, RemovalPolicy } from "aws-cdk-lib";
import * as apigw from "aws-cdk-lib/aws-apigateway";
import * as lambda from "aws-cdk-lib/aws-lambda";
import { Code, Function, Runtime } from "aws-cdk-lib/aws-lambda";
import * as s3 from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";
import * as path from "path";

// import * as sqs from 'aws-cdk-lib/aws-sqs';

export class MiwaLambdaS3Stack extends cdk.Stack {
  public readonly miwaBucket: s3.Bucket;
  public readonly greeterFn: lambda.IFunction;
  public readonly api_endpoint: string 
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const lambdaFn = new PythonFunction(this, "miwa-greeter-lambda", {
      entry: path.join(__dirname, "..", "lambda"),
      runtime: Runtime.PYTHON_3_11,
      index: "handler.py",
      handler: "lambda_handler",
      timeout: Duration.seconds(30),
      memorySize: 256,
      environment: {
        SENDGRID_API_KEY: process.env.SENDGRID_API_KEY || "",
        SENDGRID_SENDER: process.env.SENDER || "",
      },
    });
    this.greeterFn = lambdaFn;
    const api = new apigw.LambdaRestApi(this, "miwa-api", {
      handler: lambdaFn,
      proxy: false,
    });
    new cdk.CfnOutput(this, "root-endpoint", {
      value: api.url || "Something went wrong with the deploy",
    });

    // integración Lambda
    const integration = new apigw.LambdaIntegration(lambdaFn);

    // crea recurso /send y método POST
    const send = api.root.addResource("send");
    send.addMethod("POST", integration); // ← ahora el API tiene un método

    const api_endpoint = api.url! + "send"
    new cdk.CfnOutput(this, "APIEndpoint", { value: api_endpoint });
  
    this.api_endpoint = api_endpoint
    // The code that defines your stack goes here

    // example resource
    // const queue = new sqs.Queue(this, "DeploymentCdkQueue", {
    //   visibilityTimeout: cdk.Duration.seconds(300)
    // });

    // --- S3 Bucket ---
    const miwaBucket = new s3.Bucket(this, "miwa-files-bucket", {
      removalPolicy: RemovalPolicy.DESTROY, // Solo para desarrollo, en prod usar RETAIN
      autoDeleteObjects: true, // Solo para desarrollo
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
    });
    this.miwaBucket = miwaBucket;
    // Permitir a la Lambda acceso completo al bucket
    miwaBucket.grantReadWrite(lambdaFn);

    // Exportar el nombre del bucket como output
    new cdk.CfnOutput(this, "MiwaBucketName", {
      value: miwaBucket.bucketName,
      description: "Nombre del bucket S3 para archivos de Miwa",
    });
  }
}
