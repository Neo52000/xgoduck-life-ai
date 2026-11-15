#!/usr/bin/env python3
"""Simulate future XGO-Duck camera: upload a photo to Life AI using a robot API key."""
import argparse
import os
from pathlib import Path
import httpx


def main():
    p=argparse.ArgumentParser(description="Simulateur caméra XGO-Duck -> Life AI VPS")
    p.add_argument("image", type=Path, help="Fichier JPEG/PNG/WEBP")
    p.add_argument("--url", default="http://127.0.0.1:8000")
    p.add_argument("--key", default=os.getenv("ROBOT_API_KEY", ""))
    args=p.parse_args()
    if not args.key:
        p.error("Passer --key ou définir ROBOT_API_KEY")
    if not args.image.is_file():
        p.error("Image introuvable")
    ext=args.image.suffix.lower()
    mime={".jpg":"image/jpeg",".jpeg":"image/jpeg",".png":"image/png",".webp":"image/webp"}.get(ext)
    if not mime:
        p.error("Format non pris en charge")
    with args.image.open("rb") as file:
        r=httpx.post(args.url.rstrip("/")+"/api/observations",
                     files={"file": (args.image.name,file,mime)},
                     data={"source":"duck-simulator"},headers={"X-Robot-Key":args.key},timeout=30)
    r.raise_for_status()
    result=r.json()
    print("Observation envoyée :", result["id"])
    print("Statut :", result["status"])
    if result["candidate_label"]:
        print("Hypothèse à confirmer :",result["candidate_label"],"score",result["confidence"])

if __name__=="__main__":main()
