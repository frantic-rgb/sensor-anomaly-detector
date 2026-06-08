# AWS Deployment — Free Tier

Deploys the H₂ Sensor Anomaly Detector to an EC2 t2.micro instance (eligible for the AWS 12-month free tier).

## Prerequisites

- AWS account (new or less than 12 months old) for free t2.micro
- This repository pushed to GitHub

---

## Step-by-Step

### 1. Push to GitHub

```bash
git add .
git commit -m "initial commit"
git remote add origin https://github.com/frantic-rgb/sensor-anomaly-detector.git
git push -u origin main
```

### 2. Launch EC2 Instance

1. AWS Console → **EC2** → **Launch Instance**
2. Name: `sensor-anomaly-detector`
3. AMI: **Ubuntu Server 22.04 LTS** (Free tier eligible)
4. Instance type: **t2.micro** ← Free tier
5. Key pair: create new or select existing (needed for SSH access)
6. Security Group — add these inbound rules:

| Type | Port | Source    |
|------|------|-----------|
| HTTP | 80   | 0.0.0.0/0 |
| SSH  | 22   | My IP     |

7. **Advanced Details → User data**: paste the contents of `ec2-userdata.sh`  
   (edit `REPO_URL` to point to your repository first)

8. **Launch Instance**

### 3. Open the Demo

After ~3 minutes:  
→ `http://YOUR_EC2_PUBLIC_IP`  
(find the IP in EC2 Console → Instances → Public IPv4 address)

---

## Stopping the Instance (Cost Control)

Even within the free tier it is good practice to stop the instance when not in use:

```
EC2 Console → select instance → Instance state → Stop
```

> **Note:** The public IP changes on every start. Assign an Elastic IP (free while the instance is running) to keep a stable address.

---

## Local Testing

```bash
# With Docker
docker compose up --build

# Without Docker
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Both serve the app at [http://localhost:8000](http://localhost:8000).
