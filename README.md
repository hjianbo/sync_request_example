# Python 入门示例

这个目录用两个 Python 程序演示 `emqx_sync_request` 的完整流程：

```text
requester.py --HTTP API--> EMQX Sync Request --MQTT 5 请求--> client.py
       ^                                                   |
       +------------------- MQTT 5 响应 ------------------+
```

- `client.py` 是请求接收方。它使用 VIN 作为 MQTT Client ID，连接 MQTT 5，订阅 `/rpc/{vin}/sync_request`，读取请求中的 `Response Topic` 和 `Correlation Data`，然后把处理结果发布到 `/rpc/{vin}/sync_response`。
- `requester.py` 是请求发起方。它通过 EMQX Management API 调用插件，依次发送 10 个请求，并打印成功响应或 timeout 等错误。
- 每次请求的 HTTP `timeout` 会在指定范围内随机选择；接收端也会随机等待一段时间来模拟业务处理，因此可以观察成功和 `504 TIMEOUT` 两种结果。

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

默认连接参数如下：

| 参数 | 默认值 | 用途 |
| --- | --- | --- |
| MQTT 主机 | `127.0.0.1` | 接收端连接地址 |
| MQTT 端口 | `1883` | MQTT TCP 监听端口 |
| HTTP 地址 | `http://127.0.0.1:18083` | EMQX Dashboard / Management API |
| 请求主题 | `/rpc/{vin}/sync_request` | 由 VIN 决定，必须与接收端订阅主题完全一致 |
| 响应主题 | `/rpc/{vin}/sync_response` | 由 VIN 决定 |

如果 EMQX 启用了认证，可以为 MQTT 接收端设置 `EMQX_MQTT_USERNAME` 和 `EMQX_MQTT_PASSWORD`。

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

客户端会随机等待 0.5～4 秒来模拟业务处理。这个时间故意不是命令行参数，以保持首次运行命令简单。

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

`requester.py` 中保留了两个清晰的配置变量：

```python
API_KEY = os.getenv("EMQX_API_KEY", "replace-with-api-key")
SECRET_KEY = os.getenv("EMQX_SECRET_KEY", "replace-with-secret-key")
```

推荐通过环境变量提供密钥：

```bash
export EMQX_API_KEY="你的 api-key"
export EMQX_SECRET_KEY="你的 secret-key"
python requester.py --vin_list vin01,vin02,vin03
```

也可以直接修改 `requester.py` 顶部的变量。不要把真实密钥提交到 Git 仓库。

启动后，发起端会持续调用：

```http
POST /api/v5/plugin_api/emqx_sync_request/request
```

每次请求的 `timeout` 会在 1～5 秒之间随机变化。发起端默认使用 `vin01`，每次 HTTP 返回后等待 1 秒，再发送下一个请求，共发送 10 次。HTTP 客户端的网络 timeout 会比插件 timeout 多 2 秒，用来给 EMQX 返回 `504 TIMEOUT` 留出时间；真正的业务 timeout 由请求体中的 `timeout` 控制。

```bash
python requester.py
```

需要向多个 VIN 随机发送时，先为每个 VIN 分别启动一个 `client.py`，然后执行：

```bash
python requester.py --vin_list vin01,vin02,vin03
```

如果随机业务处理时间超过本次 timeout，发起端会看到类似结果：

```text
2026-07-31 12:00:01 WARNING failed status=504 code=TIMEOUT message=timeout
```

这不是 MQTT 连接断开，而是插件在指定等待时间内没有收到匹配的响应。接收端稍后发布的响应会被忽略，因为原请求已经结束。

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
- `TIMEOUT`：接收端处理时间超过本次随机 timeout，或者响应未发布到请求中的 `Response Topic`。

本示例只用于解释协议和插件调用方式。生产程序还应增加重连策略、日志、业务幂等和更严格的输入校验。
