import { Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as codebuild from 'aws-cdk-lib/aws-codebuild';
import * as codepipeline from 'aws-cdk-lib/aws-codepipeline';
import * as codepipeline_actions from 'aws-cdk-lib/aws-codepipeline-actions';

export interface MiwaBackendPipelineSourceProps {
  readonly connectionArn: string;
  readonly repositoryOwner: string;
  readonly repositoryName: string;
  readonly branch?: string;
}

export interface MiwaBackendPipelineStackProps extends StackProps {
  readonly source: MiwaBackendPipelineSourceProps;
  readonly repository: ecr.IRepository;
  readonly service: ecs.FargateService;
  readonly containerName: string;
}

export class MiwaBackendPipelineStack extends Stack {
  constructor(scope: Construct, id: string, props: MiwaBackendPipelineStackProps) {
    super(scope, id, props);

    const sourceOutput = new codepipeline.Artifact();
    const buildOutput = new codepipeline.Artifact('ImageDefinitions');

    const buildProject = new codebuild.PipelineProject(this, 'DockerBuildProject', {
      environment: {
        buildImage: codebuild.LinuxBuildImage.STANDARD_7_0,
        privileged: true,
      },
      environmentVariables: {
        REPOSITORY_URI: { value: props.repository.repositoryUri },
        CONTAINER_NAME: { value: props.containerName },
      },
      buildSpec: codebuild.BuildSpec.fromObject({
        version: '0.2',
        phases: {
          pre_build: {
            commands: [
              // Obtiene VERSION desde version.txt si existe; si no, usa el commit corto de CodeBuild
              'if [ -f version.txt ]; then VERSION="$(cat version.txt)"; else VERSION="$(echo ${CODEBUILD_RESOLVED_SOURCE_VERSION} | cut -c1-7)"; fi',
              'echo "Building version ${VERSION}"',
              'aws ecr get-login-password --region "$AWS_DEFAULT_REGION" | docker login --username AWS --password-stdin "$REPOSITORY_URI"',
            ],
          },
          build: {
            commands: [
              'docker build -t "$REPOSITORY_URI:$VERSION" -f Dockerfile .',
              'docker push "$REPOSITORY_URI:$VERSION"',
            ],
          },
          post_build: {
            commands: [
              // Generación robusta del imagedefinitions.json
              "cat > imagedefinitions.json <<'EOF'\n[\n  {\n    \"name\": \"__NAME__\",\n    \"imageUri\": \"__IMAGE__\"\n  }\n]\nEOF",
              'sed -i "s|__NAME__|${CONTAINER_NAME}|g" imagedefinitions.json',
              'sed -i "s|__IMAGE__|${REPOSITORY_URI}:${VERSION}|g" imagedefinitions.json',
              // Validación opcional (falla el build si el JSON es inválido)
              "python - <<'PY'\nimport json; json.load(open('imagedefinitions.json')); print('imagedefinitions.json OK')\nPY",
              'echo "Generated imagedefinitions.json:"',
              'cat imagedefinitions.json',
            ],
          },
        },
        artifacts: {
          files: ['imagedefinitions.json'],
        },
      }),
    });

    // Permisos para push/pull en ECR
    props.repository.grantPullPush(buildProject);

    const pipeline = new codepipeline.Pipeline(this, 'MiwaBackendPipeline', {
      crossAccountKeys: false,
    });

    pipeline.addStage({
      stageName: 'Source',
      actions: [
        new codepipeline_actions.CodeStarConnectionsSourceAction({
          actionName: 'GitHubSource',
          owner: props.source.repositoryOwner,
          repo: props.source.repositoryName,
          branch: props.source.branch ?? 'main',
          connectionArn: props.source.connectionArn,
          output: sourceOutput,
        }),
      ],
    });

    pipeline.addStage({
      stageName: 'Build',
      actions: [
        new codepipeline_actions.CodeBuildAction({
          actionName: 'DockerBuild',
          input: sourceOutput,
          project: buildProject,
          outputs: [buildOutput],
        }),
      ],
    });

    pipeline.addStage({
      stageName: 'Deploy',
      actions: [
        new codepipeline_actions.EcsDeployAction({
          actionName: 'DeployToFargate',
          service: props.service,
          input: buildOutput,
        }),
      ],
    });
  }
}
