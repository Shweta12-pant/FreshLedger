# Jenkins setup and experiment

## Prepare the host

1. Put this folder in a Git repository with `Jenkinsfile` in its root. Push it to GitHub and set the default branch to `main`. Keep `.env` and credentials off GitHub.
2. Use a Linux Jenkins agent labeled `docker` with Bash, Git, Docker Engine, the Docker Compose v2 plugin, `flock`, and access to the Docker daemon and image registry. Run the project only on a trusted agent since access to the Docker daemon can control that host. This project deploys to the same Docker host that builds and scans the image.
3. Prepare `/srv/freshledger/.env` from `.env.example` on the Docker host. Give the Jenkins agent permission to read the file and write in its parent directory. If the Quick Start demo is already using the default ports, stop it or select other ports for the deployment. The release project uses its own named volumes.
4. Connect an existing SonarQube instance or start the supplied local one with `docker compose -p freshledger-quality -f compose.quality.yaml up -d`. The default URL on that host is [localhost:9000](http://localhost:9000). Allow it to initialize, sign in with its initial credentials, change the password, and create an analysis token for the `freshledger-food-inventory` project. If Elasticsearch prevents startup, use the SonarQube host requirements for your OS. [SonarQube host requirements](https://docs.sonarsource.com/sonarqube-community-build/server-installation/pre-installation/host-requirements)

## Configure Jenkins

1. Install the Pipeline, Git, JUnit, and SonarQube Scanner for Jenkins plugins. Add the analysis token as a Jenkins **Secret text** credential.
2. Under **Manage Jenkins → System**, add a SonarQube server named **FreshLedger SonarQube**. Use a URL reachable by the Jenkins controller and agent and select the token credential. Under **Manage Jenkins → Tools**, configure a SonarScanner installation called **SonarScanner**. [Jenkins integration](https://www.jenkins.io/doc/pipeline/steps/sonar/)
3. In SonarQube, add a webhook for the project with the URL `<Jenkins base URL>/sonarqube-webhook/`. SonarQube must be able to reach the Jenkins controller at this address. If the services are on different hosts or containers, use an address reachable from both sides. [Quality gate setup](https://docs.sonarsource.com/sonarqube-server/2026.1/analyzing-source-code/ci-integration/jenkins-integration/pipeline-pause)
4. Create a **Pipeline** job, choose **Pipeline script from SCM**, enter the GitHub repository and credentials if needed, set the branch to `*/main`, and set the script path to `Jenkinsfile`. Run the job once to register the poll trigger. The Jenkinsfile polls Git for changes about every two minutes. You can configure a GitHub webhook to trigger builds sooner.
5. Run with **DEPLOY_ON_MAIN** turned off for a test-only pipeline run. With the option on, a passing main build deploys to the prepared host. The main-branch analysis setup also supports a multibranch pipeline. Non-main branches run test and image stages without using the main SonarQube project or being deployed.

## What runs on a push

| Stage | Output or gate |
| --- | --- |
| Checkout | Commit-tagged runtime and test images plus a per-build Compose project name. |
| Lint and test | Ruff, JavaScript syntax checks, and pytest against SQLite and a temporary MySQL instance. Jenkins shows the JUnit results and archives coverage. |
| SonarQube | Code analysis and the configured quality gate. A failed or timed-out gate stops the release. |
| Package | A non-root application image containing the UI, API, and forecasting worker. |
| Trivy | A vulnerability scan of the packaged image. The pipeline blocks fixable HIGH and CRITICAL findings. It archives the scan report. |
| Deploy | The tested image is started with the persistent database. The script verifies the app and monitoring endpoints and restores the previous release configuration and image if startup fails. |

The release script maintains a `current` symlink and per-release configuration under `/srv/freshledger/releases`. It leaves the database volume intact during an app rollback. Keep the active and previous image tags available on the deploy host. For this version the database is initialized with an additive schema setup. If you later add schema migrations, plan and test their rollback separately.

To inspect a deployed release from the host, use the deployment configuration from the active release.

```bash
deploy_dir=/srv/freshledger
APP_IMAGE="$(cat "$deploy_dir/current/image")" \
  docker compose --project-name freshledger-release --project-directory "$deploy_dir/current" \
  --env-file "$deploy_dir/.env" -f "$deploy_dir/current/compose.yaml" ps -a
```

## Measure for the presentation

- Use the same host, initial database state, and comparable code changes. Report the cold first start separately from warm redeploys.
- For **deployment time**, start the clock at initialization and stop when the app and monitoring checks respond. Use the same health criteria for manual trials. Jenkins records this elapsed stage time as `deploy_seconds` in `deploy.log`. To compare the full release workflow, time checkout through verification on both sides and show that separately.
- Run at least three successful trials per method and compare median times. Report successful releases over attempted releases and passing tests over total tests. Use the Jenkins build history, JUnit results, scan report, and Grafana readings as evidence.
- Show a blocked release by intentionally making a test assertion fail on a disposable branch. Then revert the change and run a successful build. Leave the main release branch and active deployment intact during this check.

| Trial | Method | Cold or warm | Deploy seconds | Tests passed / total | Released |
| --- | --- | --- | ---: | ---: | --- |
| 1 | Manual |  |  |  |  |
| 1 | Jenkins |  |  |  |  |
