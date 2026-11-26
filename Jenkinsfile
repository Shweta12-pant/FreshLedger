pipeline {
    agent { label 'docker' }

    options {
        disableConcurrentBuilds()
        timeout(time: 50, unit: 'MINUTES')
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '20'))
        skipDefaultCheckout(true)
    }

    triggers { pollSCM('H/2 * * * *') }

    parameters {
        booleanParam(name: 'DEPLOY_ON_MAIN', defaultValue: true, description: 'Release the scanned image on main.')
    }

    environment {
        TRIVY_IMAGE = 'aquasec/trivy:0.70.0'
        DEPLOY_DIR = '/srv/freshledger'
    }

    stages {
        stage('Checkout') {
            steps {
                script {
                    def scmInfo = checkout scm
                    env.CI_PROJECT = 'freshledger-ci-' + sh(
                        script: 'printf "%s:%s" "$JOB_NAME" "$BUILD_NUMBER" | sha256sum | cut -c1-14',
                        returnStdout: true
                    ).trim()
                    def tag = "${scmInfo.GIT_COMMIT.take(12)}-${env.CI_PROJECT.takeRight(14)}"
                    env.APP_IMAGE = "freshledger:${tag}"
                    env.TEST_IMAGE = "freshledger-test:${tag}"
                }
                sh 'rm -rf reports && mkdir reports'
            }
        }

        stage('Lint and automated tests') {
            steps {
                sh '''
                    set -eu
                    export CI_UID="$(id -u)" CI_GID="$(id -g)"
                    docker compose -p "$CI_PROJECT" -f compose.ci.yaml build --pull test
                    docker run --rm "$TEST_IMAGE" python -m ruff check inventory tests
                    docker run --rm -v "$PWD/inventory/static:/scripts:ro" node:22-alpine sh -ec \\
                        'for script in /scripts/*.js; do node --check "$script"; done'
                    docker compose -p "$CI_PROJECT" -f compose.ci.yaml up -d --wait --wait-timeout 150 mysql
                    docker compose -p "$CI_PROJECT" -f compose.ci.yaml run --rm --no-deps test
                '''
            }
            post {
                always {
                    junit allowEmptyResults: true, testResults: 'reports/junit.xml'
                }
            }
        }

        stage('SonarQube analysis') {
            when { expression { !env.BRANCH_NAME || env.BRANCH_NAME == 'main' } }
            steps {
                script {
                    def scanner = tool 'SonarScanner'
                    withSonarQubeEnv('FreshLedger SonarQube') {
                        withEnv(["SONAR_SCANNER_HOME=${scanner}"]) {
                            sh '"$SONAR_SCANNER_HOME/bin/sonar-scanner"'
                        }
                    }
                }
            }
        }

        stage('Quality gate') {
            when { expression { !env.BRANCH_NAME || env.BRANCH_NAME == 'main' } }
            steps {
                timeout(time: 10, unit: 'MINUTES') {
                    waitForQualityGate abortPipeline: true
                }
            }
        }

        stage('Package image') {
            steps {
                sh 'docker build --pull --target runtime --label "org.opencontainers.image.revision=$(git rev-parse HEAD)" -t "$APP_IMAGE" .'
            }
        }

        stage('Scan image with Trivy') {
            steps {
                sh '''
                    set -eu
                    trap 'rm -f reports/image.tar' EXIT
                    docker save -o reports/image.tar "$APP_IMAGE"
                    status=0
                    docker run --rm -v freshledger-trivy-cache:/root/.cache/trivy \\
                        -v "$PWD/reports/image.tar:/input/image.tar:ro" "$TRIVY_IMAGE" \\
                        image --input /input/image.tar --scanners vuln --severity HIGH,CRITICAL \\
                        --ignore-unfixed --exit-code 1 > reports/trivy.txt || status=$?
                    cat reports/trivy.txt
                    exit "$status"
                '''
            }
        }

        stage('Deploy and verify') {
            when { expression { params.DEPLOY_ON_MAIN && (!env.BRANCH_NAME || env.BRANCH_NAME == 'main') } }
            steps {
                sh '''#!/usr/bin/env bash
set -Eeuo pipefail
bash ops/deploy.sh "$APP_IMAGE" | tee reports/deploy.log
'''
            }
        }
    }

    post {
        always {
            script {
                if (env.CI_PROJECT) {
                    sh returnStatus: true, script: 'docker compose -p "$CI_PROJECT" -f compose.ci.yaml down -v --remove-orphans'
                }
            }
            archiveArtifacts allowEmptyArchive: true, artifacts: 'reports/junit.xml,reports/coverage.xml,reports/trivy.txt,reports/deploy.log'
        }
    }
}
