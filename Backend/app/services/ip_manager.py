import random
import requests


class IPManager:
    """Manages IP allocation for instances"""
    
    def __init__(self):
        # Simulated pools
        self.private_ip_pool = self._generate_private_ips()

        # Track allocations
        self.allocated_public = set()
        self.allocated_private = set()
    
    def _generate_private_ips(self):
        """Generate pool of private IPs"""
        return [f"10.0.1.{i}" for i in range(1, 255)]
    
    def allocate_public_ip(self) -> str:
        """
        Allocate the real public IP of the host machine
        """
        try:
            ip = requests.get("https://api.ipify.org").text
            self.allocated_public.add(ip)
            return ip
        except:
            # fallback if internet unavailable
            return "127.0.0.1"
    
    def allocate_private_ip(self) -> str:
        """Allocate a private IP"""
        available = [ip for ip in self.private_ip_pool if ip not in self.allocated_private]
        
        if not available:
            raise Exception("No private IPs available")
        
        ip = random.choice(available)
        self.allocated_private.add(ip)
        return ip
    
    def free_ip(self, ip: str):
        """Free an allocated IP"""
        if ip in self.allocated_public:
            self.allocated_public.remove(ip)
        elif ip in self.allocated_private:
            self.allocated_private.remove(ip)
    
    def get_allocated_ips(self):
        """Get all allocated IPs"""
        return {
            "public": list(self.allocated_public),
            "private": list(self.allocated_private)
        }