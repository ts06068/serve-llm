# serve-llm

Runpod A100 80GB 한 장에서 BF16, 32,768-token context로 vLLM을 실행합니다.
Pinggy Pro 고정 도메인을 통해 OpenAI 호환 API에 접속합니다.
32K는 입력과 생성 출력을 합친 길이입니다. 텍스트 요청을 한 번에 한 건 처리하고 나머지는 대기합니다.
배포 정보는 `runpod/deployment.json`, 실제 검증 결과는 `runpod/verification*.json`에 기록합니다.

## 켜기 · 끄기 · 사용

프로젝트 위치는 `/workspace/recap/serve-llm`입니다. 아래 스크립트는 실행 위치와 관계없이 프로젝트의
설정과 키를 읽습니다. 현재 Pod 한 개를 관리하며 새 Pod나 볼륨을 자동 생성하지 않습니다.

```bash
cd /workspace/recap/serve-llm
./start.sh                     # Pod 시작 → vLLM/Pinggy 준비 확인 (최대 20분)
./status.sh                    # Pod 상태와 인증된 endpoint 확인
python3 llm.py '한국어로 간단히 자기소개해 주세요.'
./stop.sh                      # Pod 중지, GPU 반납 (볼륨 유지)
```

```bash
./restart.sh                   # 실행 중인 컨테이너 재시작 → 재기동 확인
./start.sh --no-wait            # 시작 요청 후 바로 반환
./start.sh --timeout 1800       # 준비 확인 제한 시간 30분
./stop.sh --dry-run             # 대상만 표시, API 요청 없음
./serve.sh logs                # vLLM/Pinggy 최근 로그 (SSH 키 필요)
```

이미 실행 중인 Pod에서 `start.sh`를 다시 실행하면 모델 준비 여부만 확인합니다.
이미 중지된 Pod에서 `stop.sh`를 실행하면 추가 중지 요청을 하지 않습니다.
31B 모델 초기화가 끝나야 Pinggy 터널이 연결됩니다. 그 전에는 TLS EOF 또는 연결 실패가
표시될 수 있으며, `Waiting` 메시지는 기동 실패를 뜻하지 않습니다. 스크립트는 경과 시간과
대기 제한 시간을 표시하면서 재시도합니다. `READY`가 표시되면 사용할 수 있습니다.
시작 확인이 시간 초과되거나 Ctrl+C로 중단돼도 Pod가 자동으로 꺼지지는 않습니다.
`status.sh`로 확인하거나 `stop.sh`로 중지하세요.

`stop`은 GPU를 반납하므로 이후 `start`는 GPU 재고 부족으로 실패할 수 있습니다.
볼륨에 저장된 모델과 환경, Pinggy Pro 고정 주소는 유지합니다.
`restart`는 현재 GPU를 유지한 채 컨테이너를 재시작합니다.

## 다른 머신에서 사용

GitHub private 저장소에는 비밀키와 로컬 CLI 바이너리를 포함하지 않습니다.
Linux x86_64, Python 3.10 이상, Bash에서 다음과 같이 설치합니다.

```bash
gh repo clone ts06068/serve-llm
cd serve-llm
./setup.sh
```

`setup.sh`는 Runpod CLI 2.14.0을 공식 배포본에서 받아 SHA-256을 검증합니다.
기존 키 파일은 보존하며, 없는 설정 파일만 `.secrets/`에 만듭니다.
기존 머신의 `.secrets/`를 안전하게 직접 옮기거나 아래 항목을 채우세요.

- `.secrets/runpod.env`: Pod 관리용 `RUNPOD_API_KEY`. Pinggy 항목은 신규 배포 시 사용합니다.
- `.secrets/llm.env`: 기존 서비스의 `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL`.
- `.secrets/deployment.json`: 관리할 Pod/볼륨 ID. 설치 시 현재 배포 기록에서 복사합니다.
- `.secrets/runpod_ssh`: 현재 Pod에 등록된 SSH 비밀키. 로그 조회·업로드에 필요합니다.

```bash
chmod 700 .secrets
chmod 600 .secrets/*
./status.sh
```

기존 서비스를 이용할 때 새 LLM API 키를 임의로 만들면 터널 인증과 일치하지 않습니다.
`.secrets/llm.env`의 기존 키를 그대로 사용하세요. 시작·중지는 `RUNPOD_API_KEY`가 필요하며,
이미 켜진 LLM 호출에는 `.secrets/llm.env`만 있으면 됩니다.

## 클라이언트

```bash
python3 llm.py '한국어로 간단히 자기소개해 주세요.'
python3 llm.py --models
```

`llm.py`는 `.secrets/llm.env`를 읽으며 Python 표준 라이브러리만 사용합니다.
다른 OpenAI 호환 클라이언트에는 같은 파일의 `OPENAI_BASE_URL`, `OPENAI_API_KEY`,
`OPENAI_MODEL` 값을 사용합니다. 셸에서 사용할 때:

```bash
set -a
source .secrets/llm.env
set +a
curl --fail-with-body "$OPENAI_BASE_URL/models" \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

## Pod 관리

평소에는 루트의 `start.sh`, `stop.sh`, `restart.sh`, `status.sh`를 사용합니다.
저수준 CLI가 필요할 때는 다음 명령을 사용할 수 있습니다.

```bash
python3 runpod/control.py pod get evy0qvubbaorgx
python3 runpod/control.py pod restart evy0qvubbaorgx
python3 runpod/control.py pod stop evy0qvubbaorgx
python3 runpod/control.py pod start evy0qvubbaorgx
```

시작 명령은 `/workspace/serve/.runtime-ready`가 있으면 `boot.sh`를 실행합니다.
Supervisor가 이미지의 기존 `/start.sh`, vLLM, Pinggy를 관리합니다.
vLLM 모델 로딩 후 Pinggy 터널이 열립니다. 프로세스 종료와 터널 단절 시 자동 재시작합니다.
단, Supervisor는 응답이 멈춘 살아 있는 프로세스까지 감지하는 health watchdog은 아닙니다.

```bash
python3 runpod/remote.py 'env SERVE_DIR=/workspace/serve MANAGE_BASE=true /workspace/vllm-env/bin/supervisorctl -c /workspace/serve/supervisord.conf status'
python3 runpod/remote.py 'tail -n 40 /workspace/serve/logs/vllm.log'
python3 runpod/remote.py 'tail -n 30 /workspace/serve/logs/pinggy.log'
```

SSH 주소와 포트는 `remote.py`가 호출할 때마다 다시 조회합니다.
`restart`는 실행 중인 컨테이너를 재시작합니다. `stop`은 GPU를 반납하므로,
그 뒤의 `start`는 GPU 재고 부족으로 실패할 수 있습니다.

처음부터 새로운 Pod를 구축하는 `runpod/provision.py`는 별도 도구입니다.
현재 배포를 켜고 끄는 데는 실행하지 않습니다. 해당 도구만으로는 설치·모델 다운로드·
서비스 업로드가 완료되지 않으므로, 기록된 배포를 관리하는 위 스크립트와 구분하세요.

## 구성과 영속성

- 이미지: `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`.
- vLLM: `0.30.0+cu129`, 공식 wheel SHA-256 고정. Supervisor: `4.3.0`.
- PyTorch: `2.13.0+cu129`, torchcodec: `0.16.0+cu129`.
- 모델: `google/gemma-4-31B-it`, revision `842da3794eaa0b77d5f08bae87a17459d91ff475`.
- 기본값: BF16, TP=1, context=32768, 동시 sequence=1, GPU memory utilization=0.92.
- `/workspace`의 150GB network volume에 모델 캐시, venv, 설정, 로그를 저장합니다.
- 커널 컴파일 캐시도 `/workspace/compile-cache`에 보존합니다.
- 설치된 전체 패키지 버전은 Pod의 `/workspace/serve/installed-packages.txt`에 기록합니다.
- 튜닝 설정은 `runpod/serve/settings.env`와 Pod의 `/workspace/serve/settings.env`에 있습니다.

vLLM은 `127.0.0.1:8000`에만 바인딩하며 공개 HTTP 포트를 열지 않습니다.
Pinggy의 `k:<key>` 인증이 모든 외부 경로를 보호합니다.
Pinggy가 인증 헤더를 소비하므로, loopback에만 열린 vLLM에는 별도 API 키를 설정하지 않습니다.
Runpod 관리 API 키는 Pod에 업로드하지 않습니다. `.secrets`는 Git에서 제외합니다.

## 검증

2026-10-01 최종 Pod `evy0qvubbaorgx`(EUR-IS-1, A100 SXM 80GB × 1)에서 검증했습니다.

- 컨테이너 재시작 후 기본 서비스, vLLM, Pinggy가 자동으로 시작됐습니다.
- 고정 URL에서 모델 조회, 한국어 스트리밍 생성, 30,020-token 입력 생성이 성공했습니다.
- 인증 없는 `/health`, `/v1/models`, `/invocations` 요청은 모두 HTTP 401로 차단됐습니다.
- 30,020-token 입력은 약 19.28초에 `OK`를 반환했습니다.
- 단일 요청으로 256 tokens를 생성할 때 첫 출력 약 2.96초, 이후 약 25.32 tokens/s였습니다.
  Pinggy를 경유한 클라이언트 측 1회 측정값으로, 동시 부하나 32K 입력의 decode 속도를 측정한 값은 아닙니다.
- 최초 커널 컴파일을 포함한 이번 재시작에서 API 준비까지 약 14분 50초 걸렸습니다.
  저장된 캐시를 이후 부팅에서 재사용하도록 설정했으며, 같은 기동 시간을 보장하는 값은 아닙니다.

검증 기록: `runpod/verification.restart.json`, `runpod/restart-cycle.json`, `runpod/benchmark.json`.

```bash
python3 runpod/verify_endpoint.py
python3 runpod/verify_endpoint.py --long-context
python3 runpod/benchmark.py
python3 -m unittest discover -s tests -v
```

실제 외부 생성 응답, 인증 없는 요청 차단, 모델 tokenizer로 계산한 약 30K 입력을 확인합니다.
`serving_verified`가 false인 동안은 준비 또는 배포 중이며, 실제 서빙 완료를 의미하지 않습니다.

## 비용

GPU는 실행 중 시간당 $1.59이며, network volume과 container disk는 별도 과금됩니다.
150GB network volume은 월 환산 약 $10.50입니다.
Pod를 중지해도 network volume 저장 비용은 계속 발생합니다. Pod를 삭제해도 network volume은 남습니다.
현재 endpoint를 유지하기 위해 자동 종료 시각은 설정하지 않았습니다.

이전 EU-RO-1 Pod `rr4xzr6s02zuz4`는 중지 후 GPU 재고 부족으로 시작하지 못해 정리했습니다.
이전 150GB 볼륨 `5qhx6ugoo1`도 사용자 승인으로 삭제했고, 목록에서 제거됐음을 확인했습니다.
현재 서비스를 사용하는 볼륨은 `2h6c9qaapu`입니다.

참고: [Runpod 시작 명령](https://docs.runpod.io/pods/templates/manage-templates),
[스토리지](https://docs.runpod.io/pods/storage/types),
[네트워크 볼륨 가격](https://docs.runpod.io/storage/s3-api),
[vLLM Gemma 4](https://docs.vllm.ai/projects/recipes/en/stable/Google/Gemma4.html),
[Pinggy 인증](https://pinggy.io/docs/http_tunnels/key_auth/).
