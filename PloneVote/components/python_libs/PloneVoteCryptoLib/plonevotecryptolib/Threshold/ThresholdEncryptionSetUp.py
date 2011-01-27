# -*- coding: utf-8 -*-
#
# ============================================================================
# About this file:
# ============================================================================
#
#  ThresholdEncryptionSetUp.py : 
#  An auxiliary class used for setting up a threshold encryption scheme.
#
#  This class should be used both to generate a commitment for a threshold 
#  encryption scheme and to combine the commitments of multiple trustees in 
#  order to generate a threshold encryption private/public key pair.
#
#  Part of the PloneVote cryptographic library (PloneVoteCryptoLib)
#
#  Originally written by: Lazaro Clapp
#
# ============================================================================
# LICENSE (MIT License - http://www.opensource.org/licenses/mit-license):
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
# ============================================================================

import math

import Crypto.Hash.SHA256

from plonevotecryptolib.Threshold.Polynomial import CoefficientsPolynomial
from plonevotecryptolib.Threshold.ThresholdEncryptionCommitment import ThresholdEncryptionCommitment
from plonevotecryptolib.utilities.BitStream import BitStream

class ThresholdEncryptionSetUpStateError(Exception):
	"""
	Raised when a ThresholdEncryptionSetUp operation is called when the 
	instance is in an inappropriate state.
	
	Common examples:
		- generate_commitment called without having registered all the 
		  trustees' public keys.
		- get_fingerprint called without having registered all the trustees' 
		  commitments.
		- generate_threshold_keypair called without having registered all the 
		  trustees' commitments.				
	"""
    
	def __str__(self):
		return self.msg

	def __init__(self, msg):
		"""
		Create a new ThresholdEncryptionSetUpStateError exception.
		"""
		self.msg = msg

class IncompatibleCommitmentError(Exception):
	"""
	Raised when ThresholdEncryptionSetUp.add_trustee_commitment is given a 
	ThresholdEncryptionCommitment that is not compatible with the current 
	ThresholdEncryptionSetUp instance. 
	(ie. has a different number of trustees)
	"""
    
	def __str__(self):
		return self.msg

	def __init__(self, msg):
		"""
		Create a new IncompatibleCommitmentError exception.
		"""
		self.msg = msg


class ThresholdEncryptionSetUp:
	"""
	Used for setting up a threshold encryption scheme.
	
	This class can be used both to generate a commitment for a threshold 
	encryption scheme and to combine the commitments of multiple trustees in 
	order to generate a threshold encryption private/public key pair.
	
	ToDo: Link a comprehensive doctest file showing how this class should be 
	used.
	
	Attributes (public):
		cryptosystem::EGCryptoSystem	-- The shared cryptosystem used by the 
										   threshold scheme.
	"""
	
	def get_fingerprint(self):
		"""
		Get the fingerprint of the threshold scheme.
		
		This requires all trustees' commitments to be loaded into the current 
		instance.
		
		The same fingerprint for two different ThresholdEncryptionSetUp objects 
		indicates that all commitments have been loaded and are the same for 
		both objects. This means that both objects are starting with the same 
		information when bootstrapping the threshold encryption scheme.
		
		In order for the keys generated by 
		ThresholdEncryptionSetUp.generate_threshold_keypair to be trustworthy, 
		all trustees must generate this fingerprint and ensure that it matches 
		the fingerprint obtained by all other trustees. This guarantees that 
		all trustees are working from the same set of commitments and, thus,  
		that the threshold encryption is set up correctly.
		
		It is important that the current trustee's commitment is loaded from a 
		trusted location, rather than taken from the server, in order for this 
		verification to work.
		
		This fingerprint is calculated as a hash of all public coefficients and 
		encrypted partial private keys from all of the trustees' commitments.
		"""
		fingerprint = Crypto.Hash.SHA256.new()
		
		for commitment in self._trustees_commitments:
			if(commitment == None):
				raise ThresholdEncryptionSetUpStateError( \
					"get_fingerprint() must only be called after all the " \
					"trustees' commitments have been registered with this " \
					"ThresholdEncryptionSetUp instance. Missing at least one " \
					"commitment.")
					
			for pub_coeff in commitment.public_coefficients:
				fingerprint.update(hex(pub_coeff))
			for ciphertext in commitment.encrypted_partial_private_keys:
				for gamma, delta in ciphertext:
					fingerprint.update(hex(gamma))
					fingerprint.update(hex(delta))
					
		return fingerprint.hexdigest()
		
	
	def __init__(self, cryptosystem, num_trustees, threshold):
		"""
		Constructs a ThresholdEncryptionSetUp class.
		
		Arguments:
			cryptosystem::EGCryptoSystem	-- The cryptosystem to use for the 
											   threshold scheme.
			num_trustees::int	-- Total number of trustees in the threshold 
								   scheme. (the n in "k of n"-decryption)
			threshold::int	-- Minimum number of trustees required to decrypt 
							   threshold encrypted messages. 
							   (the k in "k of n"-decryption)
		"""
		self.cryptosystem = cryptosystem
		self._num_trustees = num_trustees
		self._threshold = threshold
		# We initialize the array of trustee public keys to None each
		self._trustees_simple_public_keys = [None for i in range(1,num_trustees + 1)]
		# Same for commitments
		self._trustees_commitments = [None for i in range(1,num_trustees + 1)]
	
	def add_trustee_public_key(self, trustee, public_key):
		"""
		Registers the (simple, 1-to-1) public key of a trustee with this object.
		
		This public keys are used to secretly transmit information only to a 
		given trustee as part of the threshold encryption set-up protocol. 
		Namely the encrypted partial private keys (P_{i}(j)), which are part of 
		the published commitment generated by each trustee, but encrypted so 
		that only the rightful recipient may read them.
		
		IMPORTANT: 
		The public keys from other trustees may be taken from the PloneVote 
		server or from some other shared storage, but it is recommended that 
		the public key for the current trustee executing the protocol be from a 
		trusted source (eg. local storage and matched to its corresponding 
		private key)
		
		Arguments:
			trustee::int	-- The index within the threshold scheme of the 
							   trustee to which the key to be registered 
							   belongs.
							   (trustees are indexed from 1 to num_trustees)
			public_key::PublicKey	-- The trustee's public key.
		"""
		if(not (1 <= trustee <= self._num_trustees)):
			raise ValueError("Invalid trustee. The threshold scheme trustees " \
							"must be indexed from 1 to %d" % self._num_trustees)
		
		# The trustee indexes go from 1 to n, the pk list indexes go from 0 to 
		# (n-1)					
		self._trustees_simple_public_keys[trustee - 1] = public_key
	
	def add_trustee_commitment(self, trustee, commitment):
		"""
		Registers the commitment of a trustee with this object.
		
		Commitments are combined in order to generate the keys for the 
		threshold encryption scheme.
		
		IMPORTANT: 
		The commitments from other trustees may be taken from the PloneVote 
		server or from some other shared storage, but it is highly recommended  
		that the commitment for the current trustee executing the protocol be  
		from a trusted source (eg. local storage). This, together with ensuring 
		that the fingerprints for the ThresholdEncryptionSetUp used by each 
		trustee to generate their keys match, can protect trustees from the 
		server or some other third party supplanting their commitments while 
		in transit.
		
		Arguments:
			trustee::int	-- The index within the threshold scheme of the 
							   trustee to which the key to be registered 
							   belongs.
							   (trustees are indexed from 1 to num_trustees)
			commitment::ThresholdEncryptionCommitment	--
							The trustee's published commitment. 
		"""
		if(not (1 <= trustee <= self._num_trustees)):
			raise ValueError("Invalid trustee. The threshold scheme trustees " \
							"must be indexed from 1 to %d" % self._num_trustees)
		
		# Check that global parameters of the commitment match those of the 
		# current ThresholdEncryptionSetUp instance.
		if(self.cryptosystem != commitment.cryptosystem):
			raise IncompatibleCommitmentError("The given commitment is not " \
							"compatible with the current " \
							"ThresholdEncryptionSetUp instance: " \
							"Different cryptosystems used.")
							
		if(self._num_trustees != commitment.num_trustees):
			raise IncompatibleCommitmentError("The given commitment is not " \
							"compatible with the current " \
							"ThresholdEncryptionSetUp instance: " \
							"Different number of trustees.")
							
		if(self._threshold != commitment.threshold):
			raise IncompatibleCommitmentError("The given commitment is not " \
							"compatible with the current " \
							"ThresholdEncryptionSetUp instance: " \
							"Different threshold value.")
		
		# The trustee indexes go from 1 to n, the commitment list indexes go 
		# from 0 to (n-1)					
		self._trustees_commitments[trustee - 1] = commitment
		
	
	def generate_commitment(self):
		"""
		Generate a ThresholdEncryptionCommitment towards the threshold scheme.
		
		Returns:
			commitment::ThresholdEncryptionCommitment
		"""
		# 0. Verify that all public keys are available for 1-to-1 encryption.
		for trustee in range(1, self._num_trustees - 1):
			# The trustee indexes go from 1 to n, the pk list indexes go from 0 
			# to (n-1)
			pk = self._trustees_simple_public_keys[trustee - 1]
			if(pk == None):
				raise ThresholdEncryptionSetUpStateError( \
					"generate_commitment() must only be called after all the " \
					"trustees' public keys have been registered with this " \
					"ThresholdEncryptionSetUp instance. Missing public key " \
					"for trustee %d." % trustee)
		
		# 1. Construct a new random polynomial of degree (threshold - 1)
		# Note: A polynomial of degree (t - 1) is determined by any t 
		# (distinct) points.
		degree = self._threshold - 1
		nbits = self.cryptosystem.get_nbits()
		prime = self.cryptosystem.get_prime()
		generator = self.cryptosystem.get_generator()
		polynomial = \
			CoefficientsPolynomial.new_random_polynomial(prime, degree)
		
		# 2. Generate the public "coefficients" (actually g^coefficient for 
		# each coefficient of the polynomial).
		public_coeficients = []
		for coeff in polynomial.get_coefficients():
			public_coeficients.append(pow(generator, coeff, prime)) 
		
		# 3. Generate the partial private keys for each trustee.
		# The partial private key for trustee j is P(j), its full private key 
		# is the sum of the P(j) values generated by all trustees 
		# (including its own).
		# IMPORTANT: We encrypt each partial private key so that only its 
		# intended recipient may read it.
		enc_keys = []
		for trustee in range(1, self._num_trustees - 1):
			pp_key = polynomial(trustee)	# P(j)
			trustee_pk = self._trustees_simple_public_keys[trustee - 1]
			
			# Note that trustee public keys need not use the same cryptosystem 
			# as the threshold encryption. In fact, they might not even have 
			# the same bit length.
			bitstream = BitStream()
			bitstream.put_num(pp_key, nbits)
			ciphertext = trustee_pk.encrypt_bitstream(bitstream)
			enc_keys.append(ciphertext)
		
		# 4. Construct a ThresholdEncryptionCommitment object storing this 
		# commitment and return it.
		return ThresholdEncryptionCommitment(self.cryptosystem, 
			self._num_trustees, self._threshold, public_coeficients, enc_keys)
	
	def generate_public_key(self):
		"""
		Construct the threshold public key for the scheme.
		
		This  method requires all trustees' commitments to be loaded into the 
		current instance. Anyone with access to all the trustees' commitments 
		can generate the public key for the threshold scheme.
		
		Returns:
			public_key::ThresholdPublicKey	-- The public key for the threshold 
											   scheme.
		"""
		pass
