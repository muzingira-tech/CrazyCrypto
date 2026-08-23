from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import os
import httpx
from web3 import AsyncWeb3
from web3.providers.async_rpc import AsyncHTTPProvider
from ens.auto import ns  # ENS convenience helper

# -----------------------------
# Network aliases / config
# -----------------------------
NETWORK_ALIASES = {
    "ethereum": "mainnet",
    "mainnet": "mainnet",
    "polygon": "polygon",
    "base": "base",
    "sepolia": "sepolia",
    "base-sepolia": "base-sepolia",
    "arbitrum": "arbitrum",
}

def resolve_network(network: str) -> str:
    return NETWORK_ALIASES.get(network, network)

RPC_URLS = {
    "mainnet": os.getenv("RPC_URL_MAINNET", os.getenv("RPC_URL")),
    "polygon": os.getenv("RPC_URL_POLYGON"),
    "base": os.getenv("RPC_URL_BASE"),
    "sepolia": os.getenv("RPC_URL_SEPOLIA"),
    "base-sepolia": os.getenv("RPC_URL_BASE_SEPOLIA"),
    "arbitrum": os.getenv("RPC_URL_ARBITRUM", "https://arb1.arbitrum.io/rpc"),
}

CHAIN_IDS = {
    "mainnet": 1,
    "polygon": 137,
    "base": 8453,
    "sepolia": 11155111,
    "base-sepolia": 84532,
    "arbitrum": 42161,
}

NATIVE_CURRENCY = {
    "mainnet": {"symbol": "ETH", "decimals": 18},
    "polygon": {"symbol": "POL", "decimals": 18},
    "base": {"symbol": "ETH", "decimals": 18},
    "sepolia": {"symbol": "ETH", "decimals": 18},
    "base-sepolia": {"symbol": "ETH", "decimals": 18},
    "arbitrum": {"symbol": "ETH", "decimals": 18},
}

app = FastAPI(title="NFT Explorer (Web3 + FastAPI)")

ERC721_ABI = [
    {"constant": True, "inputs": [{"name":"_tokenId","type":"uint256"}], "name":"tokenURI","outputs":[{"name":"","type":"string"}], "type":"function"},
    {"constant": True, "inputs": [{"name":"_tokenId","type":"uint256"}], "name":"ownerOf","outputs":[{"name":"","type":"address"}], "type":"function"},
]

class NFTMeta(BaseModel):
    token_id: int
    token_uri: Optional[str]
    metadata: Optional[dict]
    owner: Optional[str]

class ReadOnlyRPCClient:
    def __init__(self, network: str):
        network = resolve_network(network)
        rpc = RPC_URLS.get(network)
        if not rpc:
            raise ValueError(f"No RPC configured for {network}")
        self.network = network
        self.w3 = AsyncWeb3(AsyncHTTPProvider(rpc))

def get_client_sync(network: str) -> ReadOnlyRPCClient:
    network = resolve_network(network)
    if network not in RPC_URLS or not RPC_URLS[network]:
        raise HTTPException(status_code=400, detail=f"Unsupported or unconfigured network: {network}")
    return ReadOnlyRPCClient(network)

@app.get("/")
async def root():
    return {"msg": "NFT Explorer - GET /nft/{network}/{contract}/{token_id}"}

@app.get("/nft/{network}/{contract_address}/{token_id}", response_model=NFTMeta)
async def get_nft(network: str, contract_address: str, token_id: int):
    try:
        client = get_client_sync(network)
        contract = client.w3.eth.contract(address=contract_address, abi=ERC721_ABI)
        try:
            token_uri = await contract.functions.tokenURI(token_id).call()
        except Exception:
            token_uri = None
        try:
            owner = await contract.functions.ownerOf(token_id).call()
        except Exception:
            owner = None

        metadata = None
        if token_uri:
            uri = token_uri
            if uri.startswith("ipfs://"):
                uri = uri.replace("ipfs://", "https://ipfs.io/ipfs/")
            try:
                async with httpx.AsyncClient(timeout=10.0) as client_http:
                    r = await client_http.get(uri)
                    r.raise_for_status()
                    metadata = r.json()
            except Exception:
                metadata = None

        return NFTMeta(token_id=token_id, token_uri=token_uri, metadata=metadata, owner=owner)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
