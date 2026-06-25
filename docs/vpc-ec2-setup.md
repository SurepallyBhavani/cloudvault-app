## VPC + EC2 Setup
- VPC: 10.0.0.0/16, 2 public + 2 private subnets, no NAT Gateway (cost avoidance)
- EC2: t2.micro, Amazon Linux 2023, public subnet, SSH restricted to my IP
- Flask installed via pip on EC2