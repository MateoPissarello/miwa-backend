import { Duration, RemovalPolicy, Stack, StackProps, CfnOutput } from "aws-cdk-lib";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as s3n from "aws-cdk-lib/aws-s3-notifications";
import * as stepfunctions from "aws-cdk-lib/aws-stepfunctions";
import * as tasks from "aws-cdk-lib/aws-stepfunctions-tasks";
import * as lambda from "aws-cdk-lib/aws-lambda";
import { PythonFunction } from "@aws-cdk/aws-lambda-python-alpha";
import * as path from "path";
import { Construct } from "constructs";

export interface MiwaMeetingsPipelineStackProps extends StackProps {
  readonly removalPolicy?: RemovalPolicy;
  readonly allowedExtensions?: string;
}

export class MiwaMeetingsPipelineStack extends Stack {
  public readonly recordingsBucket: s3.Bucket;
  public readonly meetingTable: dynamodb.Table;
  public readonly stateMachine: stepfunctions.StateMachine;

  constructor(scope: Construct, id: string, props: MiwaMeetingsPipelineStackProps = {}) {
    super(scope, id, props);

    const bucketRemoval = props.removalPolicy ?? RemovalPolicy.RETAIN;

    this.recordingsBucket = new s3.Bucket(this, "MeetingsBucket", {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      versioned: true,
      removalPolicy: bucketRemoval,
      autoDeleteObjects: bucketRemoval === RemovalPolicy.DESTROY,
    });

    this.meetingTable = new dynamodb.Table(this, "MeetingArtifactsTable", {
      tableName: "meeting_artifacts",
      partitionKey: { name: "pk", type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: RemovalPolicy.RETAIN,
    });

    this.recordingsBucket.addToResourcePolicy(
      new iam.PolicyStatement({
        principals: [new iam.ServicePrincipal("transcribe.amazonaws.com")],
        actions: ["s3:GetObject", "s3:PutObject"],
        resources: [
          this.recordingsBucket.arnForObjects("grabaciones/*"),
          this.recordingsBucket.arnForObjects("transcripciones/raw/*"),
        ],
        conditions: {
          StringEquals: {
            "aws:SourceAccount": Stack.of(this).account,
          },
        },
      })
    );

    this.recordingsBucket.addToResourcePolicy(
      new iam.PolicyStatement({
        principals: [new iam.ServicePrincipal("transcribe.amazonaws.com")],
        actions: ["s3:ListBucket"],
        resources: [this.recordingsBucket.bucketArn],
        conditions: {
          StringEquals: {
            "aws:SourceAccount": Stack.of(this).account,
          },
        },
      })
    );

    const entryPath = path.join(__dirname, "..", "..", "backend");
    const allowedExts = props.allowedExtensions ?? ".mp3,.mp4,.m4a,.wav";

    const commonEnv = {
      DDB_TABLE_NAME: this.meetingTable.tableName,
      BUCKET_NAME: this.recordingsBucket.bucketName,
      ALLOW_EXTS: allowedExts,
    };

    const ingestFn = new PythonFunction(this, "MeetingsIngestFn", {
      entry: entryPath,
      runtime: lambda.Runtime.PYTHON_3_11,
      index: "services/meetings_service/lambda_entry.py",
      handler: "ingest",
      memorySize: 256,
      timeout: Duration.minutes(1),
      environment: commonEnv,
    });

    const startTranscriptionFn = new PythonFunction(this, "StartTranscriptionFn", {
      entry: entryPath,
      runtime: lambda.Runtime.PYTHON_3_11,
      index: "services/meetings_service/lambda_entry.py",
      handler: "start_transcription",
      memorySize: 256,
      timeout: Duration.minutes(1),
      environment: commonEnv,
    });

    const pollTranscriptionFn = new PythonFunction(this, "PollTranscriptionFn", {
      entry: entryPath,
      runtime: lambda.Runtime.PYTHON_3_11,
      index: "services/meetings_service/lambda_entry.py",
      handler: "poll_transcription",
      memorySize: 256,
      timeout: Duration.minutes(1),
      environment: commonEnv,
    });

    const storeTranscriptionFn = new PythonFunction(this, "StoreTranscriptionFn", {
      entry: entryPath,
      runtime: lambda.Runtime.PYTHON_3_11,
      index: "services/meetings_service/lambda_entry.py",
      handler: "store_transcription",
      memorySize: 512,
      timeout: Duration.minutes(5),
      environment: commonEnv,
    });

    const generateSummaryFn = new PythonFunction(this, "GenerateSummaryFn", {
      entry: entryPath,
      runtime: lambda.Runtime.PYTHON_3_11,
      index: "services/meetings_service/lambda_entry.py",
      handler: "generate_summary",
      memorySize: 512,
      timeout: Duration.minutes(5),
      environment: {
        ...commonEnv,
        LLM_MODEL_ID: "amazon.titan-text-lite-v1",
        LLM_MAX_TOKENS: "4096",
      },
    });

    this.recordingsBucket.grantReadWrite(ingestFn);
    this.recordingsBucket.grantReadWrite(startTranscriptionFn);
    this.recordingsBucket.grantReadWrite(pollTranscriptionFn);
    this.recordingsBucket.grantReadWrite(storeTranscriptionFn);
    this.recordingsBucket.grantReadWrite(generateSummaryFn);

    this.meetingTable.grantReadWriteData(ingestFn);
    this.meetingTable.grantReadWriteData(startTranscriptionFn);
    this.meetingTable.grantReadWriteData(pollTranscriptionFn);
    this.meetingTable.grantReadWriteData(storeTranscriptionFn);
    this.meetingTable.grantReadWriteData(generateSummaryFn);

    const transcribePolicy = new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ["transcribe:StartTranscriptionJob", "transcribe:GetTranscriptionJob"],
      resources: ["*"],
    });
    startTranscriptionFn.addToRolePolicy(transcribePolicy);
    pollTranscriptionFn.addToRolePolicy(transcribePolicy);

    generateSummaryFn.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
        resources: ["*"],
      })
    );

    this.recordingsBucket.addEventNotification(
      s3.EventType.OBJECT_CREATED,
      new s3n.LambdaDestination(ingestFn),
      { prefix: "grabaciones/" }
    );

    const startTranscriptionTask = new tasks.LambdaInvoke(this, "StartTranscriptionTask", {
      lambdaFunction: startTranscriptionFn,
      payload: stepfunctions.TaskInput.fromObject({
        recording_key: stepfunctions.JsonPath.stringAt("$.recording_key"),
      }),
      resultPath: "$.transcription",
      payloadResponseOnly: true,
    });

    const waitForTranscription = new stepfunctions.Wait(this, "WaitForTranscription", {
      time: stepfunctions.WaitTime.duration(Duration.seconds(30)),
    });

    const pollTranscriptionTask = new tasks.LambdaInvoke(this, "PollTranscriptionTask", {
      lambdaFunction: pollTranscriptionFn,
      payload: stepfunctions.TaskInput.fromObject({
        recording_key: stepfunctions.JsonPath.stringAt("$.recording_key"),
        job_name: stepfunctions.JsonPath.stringAt("$.transcription.job_name"),
      }),
      resultPath: "$.transcription",
      payloadResponseOnly: true,
    });

    const storeTranscriptionTask = new tasks.LambdaInvoke(this, "StoreTranscriptionTask", {
      lambdaFunction: storeTranscriptionFn,
      payload: stepfunctions.TaskInput.fromObject({
        recording_key: stepfunctions.JsonPath.stringAt("$.recording_key"),
        transcript_uri: stepfunctions.JsonPath.stringAt("$.transcription.transcript_uri"),
        language_code: stepfunctions.JsonPath.stringAt("$.transcription.language_code"),
      }),
      resultPath: stepfunctions.JsonPath.DISCARD,
      payloadResponseOnly: true,
    });

    const generateSummaryTask = new tasks.LambdaInvoke(this, "GenerateSummaryTask", {
      lambdaFunction: generateSummaryFn,
      payload: stepfunctions.TaskInput.fromObject({
        recording_key: stepfunctions.JsonPath.stringAt("$.recording_key"),
      }),
      resultPath: stepfunctions.JsonPath.DISCARD,
      payloadResponseOnly: true,
    });

    const successState = new stepfunctions.Succeed(this, "MeetingsPipelineCompleted");
    const failureState = new stepfunctions.Fail(this, "MeetingsPipelineFailed");

    const checkTranscription = new stepfunctions.Choice(this, "TranscriptionStatus");
    checkTranscription
      .when(
        stepfunctions.Condition.stringEquals("$.transcription.status", "COMPLETED"),
        storeTranscriptionTask.next(generateSummaryTask).next(successState)
      )
      .when(
        stepfunctions.Condition.stringEquals("$.transcription.status", "FAILED"),
        failureState
      )
      .otherwise(waitForTranscription);

    const definition = startTranscriptionTask
      .next(waitForTranscription)
      .next(pollTranscriptionTask)
      .next(checkTranscription);

    this.stateMachine = new stepfunctions.StateMachine(this, "MeetingsPipelineStateMachine", {
      definition,
      timeout: Duration.hours(2),
      logs: {
        destination: new logs.LogGroup(this, "MeetingsPipelineLogs", {
          retention: logs.RetentionDays.ONE_WEEK,
          removalPolicy: RemovalPolicy.DESTROY,
        }),
        level: stepfunctions.LogLevel.ALL,
      },
    });

    ingestFn.addEnvironment("PIPELINE_STATE_MACHINE_ARN", this.stateMachine.stateMachineArn);

    this.stateMachine.grantStartExecution(ingestFn);
    startTranscriptionFn.grantInvoke(this.stateMachine.role);
    pollTranscriptionFn.grantInvoke(this.stateMachine.role);
    storeTranscriptionFn.grantInvoke(this.stateMachine.role);
    generateSummaryFn.grantInvoke(this.stateMachine.role);

    new CfnOutput(this, "MeetingsBucketName", {
      value: this.recordingsBucket.bucketName,
    });
    new CfnOutput(this, "MeetingTableName", {
      value: this.meetingTable.tableName,
    });
    new CfnOutput(this, "MeetingPipelineArn", {
      value: this.stateMachine.stateMachineArn,
    });
  }
}
