# EMQX Sync Request Python 示例

这两个 Python 程序展示 `emqx_sync_request` 的完整请求和响应流程：

```text
requester.py --HTTP API--> EMQX Sync Request --MQTT 5 请求--> client.py
       ^                                                   |
       +------------------- MQTT 5 响应 ------------------+
```

- `client.py` 是请求接收方。它使用 VIN 作为 MQTT Client ID，连接 MQTT 5，订阅 `/rpc/{vin}/sync_request`，读取请求中的 `Response Topic` 和 `Correlation Data`，然后把处理结果发布到 `/rpc/{vin}/sync_response`。
- `requester.py` 是请求发起方。它通过 EMQX Management API 调用插件，依次发送 10 个请求，并打印每次响应。
- 每次请求的 HTTP `timeout` 为 6～10 秒，接收端的处理时间为 0.5～4 秒。请求 timeout 始终大于客户端的最大处理时间。

## 1. 准备环境

需要：

- Python 3.9 或更高版本
- 已安装并启用 `emqx_sync_request` 的 EMQX
- 一个拥有 `publish` 权限的 EMQX API Key

在本目录创建虚拟环境并安装依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

如果 Ubuntu 提示 `ensurepip is not available`，先安装虚拟环境组件，再重新执行上述命令：

```bash
sudo apt install python3-venv
```

默认连接参数如下：

| 参数 | 环境变量 | 默认值 |
| --- | --- | --- |
| MQTT 主机 | `EMQX_MQTT_HOST` | `127.0.0.1` |
| MQTT 端口 | `EMQX_MQTT_PORT` | `1883` |
| MQTT 用户名 | `EMQX_MQTT_USERNAME` | 未设置 |
| MQTT 密码 | `EMQX_MQTT_PASSWORD` | 未设置 |
| Management API 地址 | `EMQX_HTTP_URL` | `http://127.0.0.1:18083` |

请求主题为 `/rpc/{vin}/sync_request`，响应主题为 `/rpc/{vin}/sync_response`。请求主题必须与接收端的订阅主题完全一致。

## 2. 启动请求接收端

先启动接收端。它必须是请求主题的唯一、非共享订阅者，这是插件的路由要求：

```bash
python client.py --vin vin01
```

接收端收到请求后会打印：

1. 请求主题和 payload；
2. MQTT 5 `Response Topic`；
3. MQTT 5 `Correlation Data`；
4. 模拟业务处理耗时；
5. 发布响应。

`--vin` 同时用于：

- MQTT Client ID：`vin01`
- 请求订阅主题：`/rpc/vin01/sync_request`
- 响应主题：`/rpc/vin01/sync_response`

客户端收到请求后会等待 0.5～4 秒，再发布响应。

响应端的关键代码是：

```python
response_topic = message.properties.ResponseTopic
correlation_data = message.properties.CorrelationData
response_properties = Properties(PacketTypes.PUBLISH)
response_properties.CorrelationData = correlation_data

client.publish(
    response_topic,
    json.dumps(result).encode(),
    qos=message.qos,
    properties=response_properties,
)
```

`Response Topic` 由请求发起端设置为 `/rpc/{vin}/sync_response`。客户端回复时使用请求携带的 `Response Topic`，并把 `Correlation Data` 原样带回；插件使用这两个属性匹配原请求。

## 3. 配置 API Key 并启动请求发起端

`requester.py` 从以下环境变量读取 API Key 和 Secret Key：

```python
API_KEY = os.getenv("EMQX_API_KEY", "replace-with-api-key")
SECRET_KEY = os.getenv("EMQX_SECRET_KEY", "replace-with-secret-key")
```

在 Dashboard 的 API Key 页面创建密钥，并将 Scope 设置为 `publish`。在运行 `requester.py` 的终端中设置密钥：

```bash
export EMQX_API_KEY="你的 api-key"
export EMQX_SECRET_KEY="你的 secret-key"
python requester.py
```

`client.py` 通过 MQTT 连接 EMQX，不使用 Management API Key。如果 MQTT 监听器启用了认证，请设置 `EMQX_MQTT_USERNAME` 和 `EMQX_MQTT_PASSWORD`。

发起端调用以下接口：

```http
POST /api/v5/plugin_api/emqx_sync_request/request
```

每次请求的 `timeout` 会在 6～10 秒之间随机变化。发起端默认使用 `vin01`，每次 HTTP 返回后等待 1 秒，再发送下一个请求，共发送 10 次。HTTP 客户端的网络 timeout 比插件 timeout 多 2 秒；插件 timeout 由请求体中的 `timeout` 控制。

```bash
python requester.py
```

需要向多个 VIN 随机发送时，分别启动对应的 MQTT 客户端：

```bash
python client.py --vin vin01
python client.py --vin vin02
python client.py --vin vin03
```

每个命令需要在单独的终端运行。客户端全部连接后，执行：

```bash
python requester.py --vin_list vin01,vin02,vin03
```

## 4. 运行顺序和常见问题

建议按以下顺序操作：

```bash
cd sync_request_example
source .venv/bin/activate
python client.py --vin vin01
# 另开一个终端
python requester.py
```

常见错误：

- `NO_SUBSCRIBERS`：接收端未启动，或请求主题与订阅主题不完全相同。
- `CONFLICT`：同一请求主题存在多个精确订阅者，或使用了共享订阅。
- `BAD_API_KEY_OR_SECRET`：API Key 或 Secret Key 不正确。
- `UNAUTHORIZED_ROLE`：API Key 没有调用插件 API 所需的 `publish` 权限。
- `TIMEOUT`：接收端未在 timeout 内回复，或者响应未发布到请求中的 `Response Topic`。

程序未实现断线重连和业务幂等。将该流程用于实际业务时，需要根据设备协议补充相应处理。
